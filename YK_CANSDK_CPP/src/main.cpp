/* Small safe-by-default command-line interface for Windows commissioning.
 *
 * C++ port of yk_can_sdk/__main__.py. Same commands and arguments:
 *   ykcan_ctl --host 192.168.0.7 --port 5578 status --seconds 5
 *   ykcan_ctl move --linear 0.10 --angular 0 --duration 0.5 --arm
 */

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "ykcan/client.hpp"
#include "ykcan/config.hpp"
#include "ykcan/vehicle.hpp"

namespace {

struct Options {
    std::string host = "192.168.0.7";
    int port = 5578;
    int max_command = 300;
    std::string command;
    double seconds = 2.0;
    bool has_linear = false;
    double linear = 0.0;
    double angular = 0.0;
    double duration = 0.0;
    bool arm = false;
};

[[noreturn]] void usage(const char* argv0) {
    std::cout
        << "usage: " << argv0 << " [--host IP] [--port PORT] [--max-command N] <command> [args]\n"
        << "\n"
        << "Control/inspect a Yunkang two-driver vehicle through CAN115\n"
        << "\n"
        << "options:\n"
        << "  --host IP              CAN115 IP address (default 192.168.0.7)\n"
        << "  --port PORT            CAN115 TCP Server local port (default 5578)\n"
        << "  --max-command N        software command boundary 1..1100 (default 300)\n"
        << "\n"
        << "commands:\n"
        << "  status [--seconds S]   send safe zero commands and print feedback\n"
        << "  move --linear L [--angular A] --duration D [--arm]\n"
        << "                         perform one bounded movement; --arm is required\n"
        << "                         to acknowledge wheels are safe to move\n";
    std::exit(2);
}

double parse_double(const char* s, const char* name) {
    char* end = nullptr;
    double v = std::strtod(s, &end);
    if (end == nullptr || *end != '\0') {
        std::cerr << "error: invalid numeric value for " << name << ": " << s << "\n";
        std::exit(2);
    }
    return v;
}

int parse_int(const char* s, const char* name) {
    char* end = nullptr;
    long v = std::strtol(s, &end, 10);
    if (end == nullptr || *end != '\0') {
        std::cerr << "error: invalid integer value for " << name << ": " << s << "\n";
        std::exit(2);
    }
    return static_cast<int>(v);
}

Options parse_args(int argc, char** argv) {
    Options o;
    int i = 1;
    while (i < argc) {
        std::string arg = argv[i];
        if (arg == "--host" && i + 1 < argc) {
            o.host = argv[++i];
        } else if (arg == "--port" && i + 1 < argc) {
            o.port = parse_int(argv[++i], "--port");
        } else if (arg == "--max-command" && i + 1 < argc) {
            o.max_command = parse_int(argv[++i], "--max-command");
        } else if (arg == "--seconds" && i + 1 < argc) {
            o.seconds = parse_double(argv[++i], "--seconds");
        } else if (arg == "--linear" && i + 1 < argc) {
            o.linear = parse_double(argv[++i], "--linear");
            o.has_linear = true;
        } else if (arg == "--angular" && i + 1 < argc) {
            o.angular = parse_double(argv[++i], "--angular");
        } else if (arg == "--duration" && i + 1 < argc) {
            o.duration = parse_double(argv[++i], "--duration");
        } else if (arg == "--arm") {
            o.arm = true;
        } else if (arg == "status" || arg == "move") {
            if (!o.command.empty()) usage(argv[0]);
            o.command = arg;
        } else if (arg == "-h" || arg == "--help") {
            usage(argv[0]);
        } else {
            usage(argv[0]);
        }
        ++i;
    }
    if (o.command.empty()) usage(argv[0]);
    return o;
}

std::string repr_feedback(const yk_can::SpeedFeedback& f) {
    std::ostringstream ss;
    ss << "SpeedFeedback(motor1=" << f.motor1 << ", motor2=" << f.motor2 << ")";
    return ss.str();
}

std::string repr_feedback(const yk_can::ElectricalFeedback& f) {
    std::ostringstream ss;
    ss << "ElectricalFeedback(motor1_current_a=" << f.motor1_current_a
       << ", motor2_current_a=" << f.motor2_current_a
       << ", supply_voltage_v=" << f.supply_voltage_v << ")";
    return ss.str();
}

std::string repr_feedback(const yk_can::ThermalFaultFeedback& f) {
    std::ostringstream ss;
    ss << "ThermalFaultFeedback(motor1_temperature_c=" << f.motor1_temperature_c
       << ", motor2_temperature_c=" << f.motor2_temperature_c
       << ", motor1_faults=0x" << yk_can::hex_upper16(f.motor1_faults)
       << ", motor2_faults=0x" << yk_can::hex_upper16(f.motor2_faults) << ")";
    return ss.str();
}

std::string repr_feedback(const yk_can::PositionFeedback& f) {
    std::ostringstream ss;
    ss << "PositionFeedback(motor1=" << f.motor1 << ", motor2=" << f.motor2 << ")";
    return ss.str();
}

std::string repr_feedback(const yk_can::ParameterAck& f) {
    std::ostringstream ss;
    ss << "ParameterAck(command=0x" << std::hex << static_cast<int>(f.command)
       << ", register=0x" << f.reg << ", value=" << std::dec << f.value << ")";
    return ss.str();
}

std::string repr_feedback(const yk_can::RawFeedback& f) {
    std::ostringstream ss;
    ss << "RawFeedback(function=0x" << std::hex << static_cast<int>(f.function) << ")";
    return ss.str();
}

std::string repr_telemetry(const std::optional<yk_can::DriverTelemetry>& t) {
    if (!t.has_value()) return "None";
    std::ostringstream ss;
    ss << "DriverTelemetry(driver_id=" << static_cast<int>(t->driver_id) << ", speed=";
    if (t->speed) ss << repr_feedback(*t->speed); else ss << "None";
    ss << ", electrical=";
    if (t->electrical) ss << repr_feedback(*t->electrical); else ss << "None";
    ss << ", thermal_fault=";
    if (t->thermal_fault) ss << repr_feedback(*t->thermal_fault); else ss << "None";
    ss << ", position=";
    if (t->position) ss << repr_feedback(*t->position); else ss << "None";
    ss << ", parameter_ack=";
    if (t->parameter_ack) ss << repr_feedback(*t->parameter_ack); else ss << "None";
    ss << ")";
    return ss.str();
}

}  // namespace

int main(int argc, char** argv) {
    Options o = parse_args(argc, argv);

    yk_can::NetworkConfig network(o.host, static_cast<uint16_t>(o.port), 5.0, 0.2);
    yk_can::SafetyLimits safety(o.max_command, 0.02, 0.25, 600.0, 1200.0, 10.0, 10, 10, true);
    yk_can::VehicleConfig config(network, safety, 1, 2, 1, -1, 1, -1);

    if (o.command == "move" && !o.arm) {
        std::cerr << "Refusing movement without --arm. Lift wheels and prepare an "
                     "emergency stop first.\n";
        return 1;
    }

    yk_can::FourWheelVehicle vehicle(config);
    try {
        vehicle.connect();
        if (o.command == "move") {
            if (!o.has_linear) usage(argv[0]);
            vehicle.move_for(o.linear, o.angular, o.duration);
            return 0;
        }
        double deadline = yk_can::monotonic_seconds() + o.seconds;
        while (yk_can::monotonic_seconds() < deadline) {
            std::cout << "{\n"
                      << "  \"1\": "
                      << repr_telemetry(vehicle.client().get_telemetry(config.front_driver_id))
                      << ",\n"
                      << "  \"2\": "
                      << repr_telemetry(vehicle.client().get_telemetry(config.rear_driver_id))
                      << "\n}\n";
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
        vehicle.close();
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << "\n";
        vehicle.emergency_stop("CLI exception");
        vehicle.close();
        return 1;
    }
}
