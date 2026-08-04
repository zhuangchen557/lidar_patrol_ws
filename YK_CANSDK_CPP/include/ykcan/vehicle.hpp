#pragma once
/* High-level four-wheel vehicle controller with fail-safe command refresh.
 *
 * C++ port of yk_can_sdk/vehicle.py. Same semantics: connects, sends the
 * required zero unlock burst, runs a 50 Hz control thread with software
 * watchdog and ramp, latches emergency stop on faults, and stops with a zero
 * burst before closing the socket.
 */

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

#include "client.hpp"
#include "config.hpp"
#include "protocol.hpp"

namespace yk_can {

struct WheelCommands {
    double front_left = 0.0;
    double front_right = 0.0;
    double rear_left = 0.0;
    double rear_right = 0.0;

    bool is_zero(double tolerance = 1e-9) const {
        return std::fabs(front_left) <= tolerance && std::fabs(front_right) <= tolerance &&
               std::fabs(rear_left) <= tolerance && std::fabs(rear_right) <= tolerance;
    }

    bool operator==(const WheelCommands& o) const {
        return front_left == o.front_left && front_right == o.front_right &&
               rear_left == o.rear_left && rear_right == o.rear_right;
    }
    bool operator!=(const WheelCommands& o) const { return !(*this == o); }
};

class FourWheelVehicle {
public:
    /* Controls front driver ID 1 and rear driver ID 2 by default.
     * Public wheel commands use a vehicle-centric convention: positive means
     * the wheel drives the vehicle forward. Direction signs are applied only
     * when raw driver frames are sent. */
    FourWheelVehicle() : FourWheelVehicle(VehicleConfig(), nullptr) {}
    explicit FourWheelVehicle(VehicleConfig cfg) : FourWheelVehicle(std::move(cfg), nullptr) {}
    FourWheelVehicle(VehicleConfig cfg, GatewayClient* external_client)
        : config_(std::move(cfg)) {
        if (external_client != nullptr) {
            client_ = external_client;
        } else {
            owned_client_ = std::make_unique<GatewayClient>(config_.network);
            client_ = owned_client_.get();
        }
        callback_token_ = client_->add_feedback_callback(
            [this](const DecodedFeedback& fb) { on_feedback(fb); });
    }
    ~FourWheelVehicle() { close(); }

    FourWheelVehicle(const FourWheelVehicle&) = delete;
    FourWheelVehicle& operator=(const FourWheelVehicle&) = delete;

    bool is_connected() const { return client_->is_connected(); }

    bool estop_latched() const {
        std::lock_guard<std::recursive_mutex> lk(lock_);
        return estop_latched_;
    }

    std::string estop_reason() const {
        std::lock_guard<std::recursive_mutex> lk(lock_);
        return estop_reason_;
    }

    WheelCommands current_commands() const {
        std::lock_guard<std::recursive_mutex> lk(lock_);
        return current_;
    }

    GatewayClient& client() { return *client_; }
    const GatewayClient& client() const { return *client_; }
    const VehicleConfig& config() const { return config_; }

    /* Connect, send the required zero commands per driver, then arm. */
    void connect() {
        if (is_connected()) return;
        client_->connect();
        try {
            zero_burst_(config_.safety.unlock_repetitions);
        } catch (const std::exception&) {
            client_->close();
            throw;
        }
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            target_ = WheelCommands();
            current_ = WheelCommands();
            last_command_at_ = monotonic_seconds();
            estop_latched_ = false;
            estop_reason_.clear();
        }
        stop_flag_ = false;
        control_thread_ = std::thread([this] { control_loop(); });
    }

    /* Immediately command zero repeatedly before closing the TCP socket. */
    void close() {
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            estop_latched_ = true;
            estop_reason_ = "controller closed";
            target_ = WheelCommands();
            current_ = WheelCommands();
        }
        if (is_connected()) {
            try {
                zero_burst_(config_.safety.stop_repetitions);
            } catch (const std::exception&) {
            }
        }
        stop_flag_ = true;
        if (control_thread_.joinable()) {
            if (control_thread_.get_id() == std::this_thread::get_id()) {
                control_thread_.detach();
            } else {
                control_thread_.join();
            }
        }
        client_->close();
    }

    /* Set normalized chassis motion in [-1, 1]. Positive angular turns left. */
    WheelCommands set_motion(double linear, double angular) {
        if (linear < -1.0 || linear > 1.0 || angular < -1.0 || angular > 1.0) {
            throw ValueError("linear and angular must each be in -1.0..1.0");
        }
        double left = linear - angular;
        double right = linear + angular;
        double scale = std::max(1.0, std::max(std::fabs(left), std::fabs(right)));
        double maximum = static_cast<double>(config_.safety.max_command);
        return set_wheel_commands(left / scale * maximum, right / scale * maximum);
    }

    /* Set equal front/rear logical wheel commands, bounded by max_command. */
    WheelCommands set_wheel_commands(double left, double right) {
        return set_axle_commands(left, right, left, right);
    }

    /* Advanced four-wheel command; all values are logical vehicle directions. */
    WheelCommands set_axle_commands(double front_left, double front_right, double rear_left,
                                    double rear_right) {
        WheelCommands command(front_left, front_right, rear_left, rear_right);
        double maximum = static_cast<double>(config_.safety.max_command);
        const double values[4] = {front_left, front_right, rear_left, rear_right};
        for (double v : values) {
            if (!std::isfinite(v)) throw ValueError("wheel commands must be finite numbers");
            if (std::fabs(v) > maximum) {
                throw ValueError("wheel command exceeds configured +/-" +
                                 std::to_string(static_cast<int>(maximum)) + " boundary");
            }
        }
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            require_ready();
            target_ = command;
            last_command_at_ = monotonic_seconds();
        }
        return command;
    }

    /* Immediate, non-latching stop. Future motion remains allowed. */
    void stop() {
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            target_ = WheelCommands();
            current_ = WheelCommands();
            last_command_at_ = monotonic_seconds();
        }
        if (is_connected()) send_commands_(WheelCommands());
    }

    /* Decelerate using the configured rate, falling back to immediate stop. */
    void smooth_stop(double timeout_s = 1.0) {
        if (timeout_s <= 0) throw ValueError("timeout_s must be positive");
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            target_ = WheelCommands();
            last_command_at_ = monotonic_seconds();
        }
        double deadline = monotonic_seconds() + timeout_s;
        while (monotonic_seconds() < deadline) {
            if (current_commands().is_zero(0.5)) return;
            wait_stop_(std::min(config_.safety.command_period_s, 0.02));
        }
        stop();
    }

    /* Latch motion inhibition and issue an immediate zero burst. */
    void emergency_stop(const std::string& reason = "manual emergency stop") {
        bool should_send = false;
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            if (!estop_latched_) should_send = true;
            estop_latched_ = true;
            estop_reason_ = reason;
            target_ = WheelCommands();
            current_ = WheelCommands();
        }
        if (should_send && is_connected()) {
            try {
                zero_burst_(std::min(3, config_.safety.stop_repetitions));
            } catch (const std::exception&) {
            }
        }
    }

    /* Clear the latch only when both drivers report no active fault. */
    void clear_emergency_stop() {
        if (!is_connected()) throw ConnectionError("vehicle is not connected");
        const uint8_t ids[2] = {config_.front_driver_id, config_.rear_driver_id};
        for (uint8_t id : ids) {
            std::optional<DriverTelemetry> telemetry = client_->get_telemetry(id);
            if (telemetry.has_value() && telemetry->thermal_fault.has_value() &&
                telemetry->thermal_fault->has_fault()) {
                throw std::runtime_error("driver " + std::to_string(id) +
                                         " still reports an active fault");
            }
        }
        zero_burst_(config_.safety.unlock_repetitions);
        {
            std::lock_guard<std::recursive_mutex> lk(lock_);
            estop_latched_ = false;
            estop_reason_.clear();
            last_command_at_ = monotonic_seconds();
        }
    }

    /* Blocking bounded movement that refreshes the software watchdog. */
    void move_for(double linear, double angular, double duration_s) {
        if (duration_s <= 0 || duration_s > config_.safety.max_continuous_motion_s) {
            throw ValueError("duration_s must be > 0 and <= " +
                             std::to_string(config_.safety.max_continuous_motion_s));
        }
        double deadline = monotonic_seconds() + duration_s;
        double refresh = std::min(config_.safety.command_watchdog_s / 2.0, 0.05);
        try {
            while (monotonic_seconds() < deadline) {
                set_motion(linear, angular);
                wait_stop_(std::min(refresh, std::max(0.0, deadline - monotonic_seconds())));
            }
        } catch (const std::exception&) {
            emergency_stop("move_for interrupted");
            throw;
        }
        if (!estop_latched()) stop();
    }

    void forward(double speed = 0.2, double duration_s = 1.0) {
        move_for(std::fabs(speed), 0.0, duration_s);
    }
    void backward(double speed = 0.2, double duration_s = 1.0) {
        move_for(-std::fabs(speed), 0.0, duration_s);
    }
    void turn_left(double speed = 0.2, double turn = 0.1, double duration_s = 1.0) {
        move_for(std::fabs(speed), std::fabs(turn), duration_s);
    }
    void turn_right(double speed = 0.2, double turn = 0.1, double duration_s = 1.0) {
        move_for(std::fabs(speed), -std::fabs(turn), duration_s);
    }
    void spin_left(double speed = 0.2, double duration_s = 1.0) {
        move_for(0.0, std::fabs(speed), duration_s);
    }
    void spin_right(double speed = 0.2, double duration_s = 1.0) {
        move_for(0.0, -std::fabs(speed), duration_s);
    }

    /* Latest speed feedback converted to vehicle-forward signs; nullopt when
     * both drivers do not yet have speed feedback. */
    std::optional<WheelCommands> get_logical_wheel_speeds() const {
        const VehicleConfig& cfg = config_;
        std::optional<DriverTelemetry> front = client_->get_telemetry(cfg.front_driver_id);
        std::optional<DriverTelemetry> rear = client_->get_telemetry(cfg.rear_driver_id);
        if (!front.has_value() || !rear.has_value() || !front->speed.has_value() ||
            !rear->speed.has_value()) {
            return std::nullopt;
        }
        WheelCommands out;
        out.front_left = front->speed->motor1 * cfg.front_motor1_sign;
        out.front_right = front->speed->motor2 * cfg.front_motor2_sign;
        out.rear_left = rear->speed->motor1 * cfg.rear_motor1_sign;
        out.rear_right = rear->speed->motor2 * cfg.rear_motor2_sign;
        return out;
    }

    /* Latest position counts converted to vehicle-forward signs. */
    std::optional<WheelCommands> get_logical_wheel_positions() const {
        const VehicleConfig& cfg = config_;
        std::optional<DriverTelemetry> front = client_->get_telemetry(cfg.front_driver_id);
        std::optional<DriverTelemetry> rear = client_->get_telemetry(cfg.rear_driver_id);
        if (!front.has_value() || !rear.has_value() || !front->position.has_value() ||
            !rear->position.has_value()) {
            return std::nullopt;
        }
        WheelCommands out;
        out.front_left = front->position->motor1 * cfg.front_motor1_sign;
        out.front_right = front->position->motor2 * cfg.front_motor2_sign;
        out.rear_left = rear->position->motor1 * cfg.rear_motor1_sign;
        out.rear_right = rear->position->motor2 * cfg.rear_motor2_sign;
        return out;
    }

private:
    void control_loop() {
        double period = config_.safety.command_period_s;
        double next_tick = monotonic_seconds();
        while (!stop_flag_.load()) {
            double now = monotonic_seconds();
            WheelCommands command;
            {
                std::lock_guard<std::recursive_mutex> lk(lock_);
                bool stale =
                    (now - last_command_at_) > config_.safety.command_watchdog_s;
                bool immediate = stale || estop_latched_;
                WheelCommands desired = immediate ? WheelCommands() : target_;
                current_ = immediate ? WheelCommands() : ramp_(current_, desired, period);
                command = current_;
            }
            try {
                send_commands_(command);
            } catch (const std::exception& exc) {
                emergency_stop(std::string("network send failed: ") + exc.what());
                stop_flag_ = true;
                return;
            }
            next_tick += period;
            double delay = next_tick - monotonic_seconds();
            if (delay <= 0) {
                next_tick = monotonic_seconds();
                continue;
            }
            wait_stop_(delay);
        }
    }

    static double ramp_step_(double old_v, double new_v, double rate_per_s, double period) {
        double delta = rate_per_s * period;
        if (new_v > old_v) return std::min(new_v, old_v + delta);
        return std::max(new_v, old_v - delta);
    }

    WheelCommands ramp_(const WheelCommands& current, const WheelCommands& target,
                        double period) const {
        const SafetyLimits& s = config_.safety;
        auto step = [&](double old_v, double new_v) {
            bool accelerating = std::fabs(new_v) > std::fabs(old_v) && old_v * new_v >= 0;
            double rate =
                accelerating ? s.max_acceleration_per_s : s.max_deceleration_per_s;
            return ramp_step_(old_v, new_v, rate, period);
        };
        WheelCommands out;
        out.front_left = step(current.front_left, target.front_left);
        out.front_right = step(current.front_right, target.front_right);
        out.rear_left = step(current.rear_left, target.rear_left);
        out.rear_right = step(current.rear_right, target.rear_right);
        return out;
    }

    void send_commands_(const WheelCommands& command) {
        const VehicleConfig& cfg = config_;
        client_->send_motor_raw(cfg.front_driver_id,
                                static_cast<int32_t>(std::llround(command.front_left)) *
                                    cfg.front_motor1_sign,
                                static_cast<int32_t>(std::llround(command.front_right)) *
                                    cfg.front_motor2_sign);
        client_->send_motor_raw(cfg.rear_driver_id,
                                static_cast<int32_t>(std::llround(command.rear_left)) *
                                    cfg.rear_motor1_sign,
                                static_cast<int32_t>(std::llround(command.rear_right)) *
                                    cfg.rear_motor2_sign);
    }

    void zero_burst_(int repetitions) {
        for (int i = 0; i < repetitions; ++i) {
            send_commands_(WheelCommands());
            wait_stop_(config_.safety.command_period_s);
        }
    }

    void on_feedback(const DecodedFeedback& fb) {
        if (!config_.safety.auto_estop_on_fault) return;
        const ThermalFaultFeedback* tf = std::get_if<ThermalFaultFeedback>(&fb);
        if (tf == nullptr || !tf->has_fault()) return;
        std::vector<std::string> labels = fault_labels_zh(tf->motor1_faults);
        std::vector<std::string> labels2 = fault_labels_zh(tf->motor2_faults);
        labels.insert(labels.end(), labels2.begin(), labels2.end());
        std::string detail;
        for (size_t i = 0; i < labels.size(); ++i) {
            if (i) detail += ", ";
            detail += labels[i];
        }
        if (detail.empty()) {
            detail = "unknown bits m1=0x" + hex_upper16(tf->motor1_faults) + ", m2=0x" +
                     hex_upper16(tf->motor2_faults);
        }
        emergency_stop("driver " + std::to_string(tf->meta.driver_id) + " fault: " + detail);
    }

    void require_ready() {
        if (!is_connected()) throw ConnectionError("vehicle is not connected");
        if (estop_latched_) {
            throw std::runtime_error("emergency stop is latched: " + estop_reason_);
        }
    }

    /* Sleep for at most 'seconds', returning early when stop_flag_ is set. */
    void wait_stop_(double seconds) {
        double deadline = monotonic_seconds() + std::max(0.0, seconds);
        while (monotonic_seconds() < deadline) {
            if (stop_flag_.load()) return;
            double remaining = deadline - monotonic_seconds();
            std::this_thread::sleep_for(std::chrono::milliseconds(
                std::max(1LL, static_cast<long long>(remaining * 1000.0))));
        }
    }

    VehicleConfig config_;
    std::unique_ptr<GatewayClient> owned_client_;
    GatewayClient* client_ = nullptr;
    mutable std::recursive_mutex lock_;
    std::atomic<bool> stop_flag_{false};
    std::thread control_thread_;
    WheelCommands target_;
    WheelCommands current_;
    double last_command_at_ = 0.0;
    bool estop_latched_ = true;
    std::string estop_reason_ = "not connected";
    uint64_t callback_token_ = 0;
};

}  // namespace yk_can