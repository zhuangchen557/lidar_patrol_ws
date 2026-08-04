#pragma once
/* Validated SDK configuration with conservative movement defaults.
 *
 * C++ port of yk_can_sdk/config.py: NetworkConfig, SafetyLimits and
 * VehicleConfig keep the same fields, defaults, validation rules and JSON
 * schema as the Python gold reference implementation.
 */

#include <cstdint>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "json.hpp"

namespace yk_can {

class NetworkConfig {
public:
    std::string host = "192.168.0.7";
    uint16_t port = 5578;
    double connect_timeout_s = 5.0;
    double receive_timeout_s = 0.2;

    NetworkConfig() = default;
    NetworkConfig(std::string host_, uint16_t port_, double connect_timeout_s_,
                  double receive_timeout_s_)
        : host(std::move(host_)),
          port(port_),
          connect_timeout_s(connect_timeout_s_),
          receive_timeout_s(receive_timeout_s_) {
        validate();
    }

    void validate() const {
        std::string trimmed = host;
        // Python does host.strip(); blank host is rejected.
        size_t b = trimmed.find_first_not_of(" \t\r\n");
        if (b == std::string::npos || trimmed.empty()) {
            throw std::runtime_error("host must not be empty");
        }
        if (port < 1 || port > 65535) throw std::runtime_error("port must be in 1..65535");
        if (connect_timeout_s <= 0 || receive_timeout_s <= 0) {
            throw std::runtime_error("socket timeouts must be positive");
        }
    }
};

class SafetyLimits {
public:
    int max_command = 300;
    double command_period_s = 0.02;
    double command_watchdog_s = 0.25;
    double max_acceleration_per_s = 600.0;
    double max_deceleration_per_s = 1200.0;
    double max_continuous_motion_s = 10.0;
    int unlock_repetitions = 10;
    int stop_repetitions = 10;
    bool auto_estop_on_fault = true;

    SafetyLimits() = default;
    SafetyLimits(int max_command_, double period, double watchdog, double accel, double decel,
                 double max_continuous, int unlock, int stop, bool auto_estop)
        : max_command(max_command_),
          command_period_s(period),
          command_watchdog_s(watchdog),
          max_acceleration_per_s(accel),
          max_deceleration_per_s(decel),
          max_continuous_motion_s(max_continuous),
          unlock_repetitions(unlock),
          stop_repetitions(stop),
          auto_estop_on_fault(auto_estop) {
        validate();
    }

    void validate() const {
        if (max_command < 1 || max_command > 1100) {
            throw std::runtime_error("max_command must be in 1..1100 for open-loop mode");
        }
        if (command_period_s < 0.01 || command_period_s > 0.1) {
            throw std::runtime_error("command_period_s must be in 0.01..0.1 seconds");
        }
        if (!(command_period_s < command_watchdog_s && command_watchdog_s < 0.5)) {
            throw std::runtime_error(
                "command_watchdog_s must be greater than the period and below 0.5 s");
        }
        if (max_acceleration_per_s <= 0 || max_deceleration_per_s <= 0) {
            throw std::runtime_error("acceleration and deceleration limits must be positive");
        }
        if (max_continuous_motion_s <= 0) {
            throw std::runtime_error("max_continuous_motion_s must be positive");
        }
        if (unlock_repetitions < 10 || unlock_repetitions > 100) {
            throw std::runtime_error("unlock_repetitions must be in 10..100");
        }
        if (stop_repetitions < 1 || stop_repetitions > 100) {
            throw std::runtime_error("stop_repetitions must be in 1..100");
        }
    }
};

class VehicleConfig {
public:
    NetworkConfig network;
    SafetyLimits safety;
    uint8_t front_driver_id = 1;
    uint8_t rear_driver_id = 2;
    int8_t front_motor1_sign = 1;
    int8_t front_motor2_sign = -1;
    int8_t rear_motor1_sign = 1;
    int8_t rear_motor2_sign = -1;

    VehicleConfig() { validate(); }
    VehicleConfig(NetworkConfig network_, SafetyLimits safety_, uint8_t front_id, uint8_t rear_id,
                  int8_t f1, int8_t f2, int8_t r1, int8_t r2)
        : network(std::move(network_)),
          safety(std::move(safety_)),
          front_driver_id(front_id),
          rear_driver_id(rear_id),
          front_motor1_sign(f1),
          front_motor2_sign(f2),
          rear_motor1_sign(r1),
          rear_motor2_sign(r2) {
        validate();
    }

    void validate() const {
        if (front_driver_id < 1 || front_driver_id > 100 || rear_driver_id < 1 ||
            rear_driver_id > 100) {
            throw std::runtime_error("driver IDs must be in 1..100");
        }
        if (front_driver_id == rear_driver_id) {
            throw std::runtime_error("front and rear driver IDs must be different");
        }
        const int8_t signs[] = {front_motor1_sign, front_motor2_sign, rear_motor1_sign,
                                rear_motor2_sign};
        for (int8_t s : signs) {
            if (s != -1 && s != 1) throw std::runtime_error("motor direction signs must be +1 or -1");
        }
    }

    /* Loads a VehicleConfig JSON file; schema identical to config.example.json
     * consumed by VehicleConfig.from_json in the Python reference. */
    static VehicleConfig from_json(const std::string& path) {
        std::ifstream file(path);
        if (!file) {
            throw std::runtime_error("cannot open config file: " + path);
        }
        std::stringstream ss;
        ss << file.rdbuf();
        return from_json_string(ss.str());
    }

    static VehicleConfig from_json_string(const std::string& text) {
        json::Value root = json::Value::parse(text);
        if (!root.is_object()) throw std::runtime_error("config root must be a JSON object");

        VehicleConfig cfg;

        const json::Value* net = root.find("network");
        if (net != nullptr && !net->is_null()) {
            if (!net->is_object()) throw std::runtime_error("'network' must be an object");
            cfg.network.host = net->find("host") ? net->find("host")->string_or("192.168.0.7")
                                                 : cfg.network.host;
            if (net->find("port")) cfg.network.port = static_cast<uint16_t>(net->find("port")->int_or(5578));
            if (net->find("connect_timeout_s")) cfg.network.connect_timeout_s = net->find("connect_timeout_s")->number_or(cfg.network.connect_timeout_s);
            if (net->find("receive_timeout_s")) cfg.network.receive_timeout_s = net->find("receive_timeout_s")->number_or(cfg.network.receive_timeout_s);
            cfg.network.validate();
        }

        const json::Value* saf = root.find("safety");
        if (saf != nullptr && !saf->is_null()) {
            if (!saf->is_object()) throw std::runtime_error("'safety' must be an object");
            auto load_int = [saf](const char* key, int fallback) {
                const json::Value* v = saf->find(key);
                return v ? v->int_or(fallback) : fallback;
            };
            auto load_num = [saf](const char* key, double fallback) {
                const json::Value* v = saf->find(key);
                return v ? v->number_or(fallback) : fallback;
            };
            auto load_bool = [saf](const char* key, bool fallback) {
                const json::Value* v = saf->find(key);
                return v ? v->bool_or(fallback) : fallback;
            };
            cfg.safety.max_command = load_int("max_command", 300);
            cfg.safety.command_period_s = load_num("command_period_s", 0.02);
            cfg.safety.command_watchdog_s = load_num("command_watchdog_s", 0.25);
            cfg.safety.max_acceleration_per_s = load_num("max_acceleration_per_s", 600.0);
            cfg.safety.max_deceleration_per_s = load_num("max_deceleration_per_s", 1200.0);
            cfg.safety.max_continuous_motion_s = load_num("max_continuous_motion_s", 10.0);
            cfg.safety.unlock_repetitions = load_int("unlock_repetitions", 10);
            cfg.safety.stop_repetitions = load_int("stop_repetitions", 10);
            cfg.safety.auto_estop_on_fault = load_bool("auto_estop_on_fault", true);
            cfg.safety.validate();
        }

        if (root.find("front_driver_id")) cfg.front_driver_id = static_cast<uint8_t>(root.find("front_driver_id")->int_or(1));
        if (root.find("rear_driver_id")) cfg.rear_driver_id = static_cast<uint8_t>(root.find("rear_driver_id")->int_or(2));
        if (root.find("front_motor1_sign")) cfg.front_motor1_sign = static_cast<int8_t>(root.find("front_motor1_sign")->int_or(1));
        if (root.find("front_motor2_sign")) cfg.front_motor2_sign = static_cast<int8_t>(root.find("front_motor2_sign")->int_or(-1));
        if (root.find("rear_motor1_sign")) cfg.rear_motor1_sign = static_cast<int8_t>(root.find("rear_motor1_sign")->int_or(1));
        if (root.find("rear_motor2_sign")) cfg.rear_motor2_sign = static_cast<int8_t>(root.find("rear_motor2_sign")->int_or(-1));

        cfg.validate();
        return cfg;
    }

    json::Value to_json() const {
        json::Value root = json::Value::object();
        json::Value net = json::Value::object();
        net.insert("host", json::Value::string(network.host));
        net.insert("port", json::Value::number(network.port));
        net.insert("connect_timeout_s", json::Value::number(network.connect_timeout_s));
        net.insert("receive_timeout_s", json::Value::number(network.receive_timeout_s));
        root.insert("network", std::move(net));

        json::Value saf = json::Value::object();
        saf.insert("max_command", json::Value::number(safety.max_command));
        saf.insert("command_period_s", json::Value::number(safety.command_period_s));
        saf.insert("command_watchdog_s", json::Value::number(safety.command_watchdog_s));
        saf.insert("max_acceleration_per_s", json::Value::number(safety.max_acceleration_per_s));
        saf.insert("max_deceleration_per_s", json::Value::number(safety.max_deceleration_per_s));
        saf.insert("max_continuous_motion_s", json::Value::number(safety.max_continuous_motion_s));
        saf.insert("unlock_repetitions", json::Value::number(safety.unlock_repetitions));
        saf.insert("stop_repetitions", json::Value::number(safety.stop_repetitions));
        saf.insert("auto_estop_on_fault", json::Value::boolean(safety.auto_estop_on_fault));
        root.insert("safety", std::move(saf));

        root.insert("front_driver_id", json::Value::number(front_driver_id));
        root.insert("rear_driver_id", json::Value::number(rear_driver_id));
        root.insert("front_motor1_sign", json::Value::number(front_motor1_sign));
        root.insert("front_motor2_sign", json::Value::number(front_motor2_sign));
        root.insert("rear_motor1_sign", json::Value::number(rear_motor1_sign));
        root.insert("rear_motor2_sign", json::Value::number(rear_motor2_sign));
        return root;
    }

    std::string to_json_string(bool pretty = true) const { return to_json().dump(pretty); }
};

}  // namespace yk_can