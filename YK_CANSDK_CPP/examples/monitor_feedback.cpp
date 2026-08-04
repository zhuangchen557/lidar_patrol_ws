/* Keep both drivers stopped and print parsed feedback.
 * C++ port of examples/monitor_feedback.py.
 */

#include <chrono>
#include <cstdint>
#include <iostream>
#include <thread>

#include "ykcan/client.hpp"
#include "ykcan/vehicle.hpp"

namespace {

std::string telemetry_summary(const std::optional<yk_can::DriverTelemetry>& t) {
    if (!t.has_value()) return "None";
    std::string out = "DriverTelemetry(driver_id=" + std::to_string(t->driver_id) + ", ";
    if (t->speed) {
        out += "speed(" + std::to_string(t->speed->motor1) + "," +
               std::to_string(t->speed->motor2) + ")";
    } else {
        out += "speed=None";
    }
    if (t->electrical) {
        out += ", electrical(cur1=" + std::to_string(t->electrical->motor1_current_a) +
               ", cur2=" + std::to_string(t->electrical->motor2_current_a) +
               ", v=" + std::to_string(t->electrical->supply_voltage_v) + ")";
    }
    if (t->thermal_fault) {
        out += ", faults(m1=0x" + yk_can::hex_upper16(t->thermal_fault->motor1_faults) +
               ", m2=0x" + yk_can::hex_upper16(t->thermal_fault->motor2_faults) + ")";
    }
    if (t->position) {
        out += ", position(" + std::to_string(t->position->motor1) + "," +
               std::to_string(t->position->motor2) + ")";
    }
    out += ")";
    return out;
}

}  // namespace

int main() {
    try {
        yk_can::VehicleConfig config = yk_can::VehicleConfig::from_json("config.example.json");
        yk_can::FourWheelVehicle car(config);
        car.connect();
        std::cout << "Connected. Press Ctrl+C to exit; zero commands continue at 50 Hz.\n";
        for (;;) {
            std::cout << telemetry_summary(car.client().get_telemetry(config.front_driver_id))
                      << "\n";
            std::cout << telemetry_summary(car.client().get_telemetry(config.rear_driver_id))
                      << "\n";
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << "\n";
        return 1;
    }
}
