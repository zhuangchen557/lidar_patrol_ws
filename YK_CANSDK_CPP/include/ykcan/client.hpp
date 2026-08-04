#pragma once
/* Thread-safe TCP client for a CAN115 configured as TCP Server.
 *
 * C++ port of yk_can_sdk/client.py. Owns the TCP connection, the receive
 * thread, the CanStreamParser and the per-driver telemetry cache. Behaviour
 * mirrors the Python reference: same connect/close semantics, same callback
 * isolation, same error recording.
 */

#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <variant>
#include <vector>

#include "config.hpp"
#include "net.hpp"
#include "protocol.hpp"

namespace yk_can {

struct DriverTelemetry {
    uint8_t driver_id = 0;
    std::optional<SpeedFeedback> speed;
    std::optional<ElectricalFeedback> electrical;
    std::optional<ThermalFaultFeedback> thermal_fault;
    std::optional<PositionFeedback> position;
    std::optional<ParameterAck> parameter_ack;

    /* Latest received_monotonic across all cached feedback types, or nullopt. */
    std::optional<double> last_update_monotonic() const {
        double best = -1.0;
        bool any = false;
        auto consider = [&](const std::optional<double>& ts) {
            if (ts.has_value()) {
                if (!any || *ts > best) best = *ts;
                any = true;
            }
        };
        if (speed) consider(speed->meta.received_monotonic);
        if (electrical) consider(electrical->meta.received_monotonic);
        if (thermal_fault) consider(thermal_fault->meta.received_monotonic);
        if (position) consider(position->meta.received_monotonic);
        if (parameter_ack) consider(parameter_ack->meta.received_monotonic);
        if (!any) return std::nullopt;
        return std::optional<double>(best);
    }
};

using FeedbackCallback = std::function<void(const DecodedFeedback&)>;

class GatewayClient {
public:
    explicit GatewayClient(NetworkConfig cfg = NetworkConfig()) : config_(std::move(cfg)) {}
    ~GatewayClient() { close(); }

    GatewayClient(const GatewayClient&) = delete;
    GatewayClient& operator=(const GatewayClient&) = delete;

    bool is_connected() const { return connected_.load(); }

    std::string last_error() const {
        std::lock_guard<std::mutex> lk(state_mutex_);
        return last_error_;
    }

    void connect() {
        if (is_connected()) return;
        TcpSocket sock = TcpSocket::connect(config_.host, config_.port, config_.connect_timeout_s);
        sock.set_receive_timeout(config_.receive_timeout_s);
        {
            std::lock_guard<std::mutex> lk(state_mutex_);
            socket_ = std::make_shared<TcpSocket>(std::move(sock));
            last_error_.clear();
            parser_.clear();
        }
        stop_flag_ = false;
        connected_ = true;
        receiver_ = std::thread([this] { receive_loop(); });
    }

    void close() {
        stop_flag_ = true;
        connected_ = false;
        std::shared_ptr<TcpSocket> sock;
        {
            std::lock_guard<std::mutex> lk(state_mutex_);
            sock = std::move(socket_);
        }
        if (sock) {
            sock->shutdown_both();
            sock->close();
        }
        if (receiver_.joinable()) {
            if (receiver_.get_id() == std::this_thread::get_id()) {
                receiver_.detach();  /* close() called from a feedback callback */
            } else {
                receiver_.join();
            }
        }
    }

    /* Returns an opaque registration token used by remove_feedback_callback. */
    uint64_t add_feedback_callback(FeedbackCallback cb) {
        std::lock_guard<std::mutex> lk(state_mutex_);
        uint64_t token = next_token_++;
        callbacks_.emplace_back(token, std::move(cb));
        return token;
    }

    bool remove_feedback_callback(uint64_t token) {
        std::lock_guard<std::mutex> lk(state_mutex_);
        for (auto it = callbacks_.begin(); it != callbacks_.end(); ++it) {
            if (it->first == token) {
                callbacks_.erase(it);
                return true;
            }
        }
        return false;
    }

    void send_frame(const CanFrame& frame) {
        std::array<uint8_t, kGatewayFrameSize> packet = frame.to_gateway_bytes();
        std::lock_guard<std::mutex> lk(send_mutex_);
        std::shared_ptr<TcpSocket> sock = current_socket();
        if (!sock || !is_connected()) {
            throw ConnectionError("CAN115 TCP client is not connected");
        }
        try {
            sock->send_all(packet.data(), packet.size());
        } catch (const std::exception& exc) {
            record_error(exc.what());
            throw ConnectionError(std::string("failed to send to CAN115: ") + exc.what());
        }
    }

    void send_motor_raw(uint8_t driver_id, int32_t motor1, int32_t motor2) {
        send_frame(build_motor_frame(driver_id, motor1, motor2));
    }

    std::optional<DriverTelemetry> get_telemetry(uint8_t driver_id) const {
        std::lock_guard<std::mutex> lk(state_mutex_);
        auto it = telemetry_.find(driver_id);
        if (it == telemetry_.end()) return std::nullopt;
        return it->second;  /* value copy: thread-safe snapshot */
    }

    std::optional<DriverTelemetry> wait_for_feedback(uint8_t driver_id, double timeout_s) {
        if (timeout_s <= 0) throw std::runtime_error("timeout_s must be positive");
        double deadline = monotonic_seconds() + timeout_s;
        while (true) {
            std::optional<DriverTelemetry> t = get_telemetry(driver_id);
            if (t.has_value() && t->last_update_monotonic().has_value()) return t;
            if (stop_flag_.load()) break;
            if (monotonic_seconds() >= deadline) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        return std::nullopt;
    }

    CanStreamParser& parser() { return parser_; }
    const CanStreamParser& parser() const { return parser_; }

private:
    std::shared_ptr<TcpSocket> current_socket() {
        std::lock_guard<std::mutex> lk(state_mutex_);
        return socket_;
    }

    void record_error(const std::string& message) {
        {
            std::lock_guard<std::mutex> lk(state_mutex_);
            last_error_ = message;
        }
        connected_ = false;
    }

    void receive_loop() {
        try {
            while (!stop_flag_.load()) {
                std::shared_ptr<TcpSocket> sock = current_socket();
                if (!sock) return;
                std::vector<uint8_t> chunk(4096);
                ptrdiff_t n = sock->recv(chunk.data(), chunk.size());
                if (n == -1) continue;  /* receive timeout: keep polling */
                if (n == 0) throw ConnectionError("CAN115 closed the TCP connection");
                double now = monotonic_seconds();
                for (CanFrame& frame : parser_.feed(chunk.data(), static_cast<size_t>(n))) {
                    try {
                        DecodedFeedback fb = decode_feedback(frame, now);
                        store_feedback(fb);
                    } catch (const ValueError&) {
                        continue;
                    }
                }
            }
        } catch (const std::exception& exc) {
            if (!stop_flag_.load()) record_error(exc.what());
        }
        connected_ = false;
        std::shared_ptr<TcpSocket> sock;
        {
            std::lock_guard<std::mutex> lk(state_mutex_);
            sock = std::move(socket_);
        }
        if (sock) {
            sock->shutdown_both();
            sock->close();
        }
    }

    void store_feedback(const DecodedFeedback& fb) {
        std::vector<FeedbackCallback> snapshot;
        {
            std::lock_guard<std::mutex> lk(state_mutex_);
            uint8_t id = 0;
            std::visit([&](const auto& f) { id = f.meta.driver_id; }, fb);
            DriverTelemetry& item = telemetry_[id];
            if (item.driver_id == 0) item.driver_id = id;
            if (const auto* p = std::get_if<SpeedFeedback>(&fb)) item.speed = *p;
            else if (const auto* p = std::get_if<ElectricalFeedback>(&fb)) item.electrical = *p;
            else if (const auto* p = std::get_if<ThermalFaultFeedback>(&fb)) item.thermal_fault = *p;
            else if (const auto* p = std::get_if<PositionFeedback>(&fb)) item.position = *p;
            else if (const auto* p = std::get_if<ParameterAck>(&fb)) item.parameter_ack = *p;
            snapshot.reserve(callbacks_.size());
            for (const auto& kv : callbacks_) snapshot.push_back(kv.second);
        }
        /* User callbacks must never kill the receive thread. */
        for (const auto& cb : snapshot) {
            try {
                cb(fb);
            } catch (...) {
            }
        }
    }

    NetworkConfig config_;
    mutable std::mutex state_mutex_;
    std::mutex send_mutex_;
    std::atomic<bool> stop_flag_{false};
    std::atomic<bool> connected_{false};
    std::thread receiver_;
    std::shared_ptr<TcpSocket> socket_;
    std::unordered_map<uint8_t, DriverTelemetry> telemetry_;
    std::vector<std::pair<uint64_t, FeedbackCallback>> callbacks_;
    uint64_t next_token_ = 1;
    std::string last_error_;
    CanStreamParser parser_;
};

}  // namespace yk_can