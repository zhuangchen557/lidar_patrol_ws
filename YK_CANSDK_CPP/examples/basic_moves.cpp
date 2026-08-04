/* Low-speed movement examples. Run only after the commissioning checklist.
 * C++ port of examples/basic_moves.py.
 */

#include <iostream>

#include "ykcan/vehicle.hpp"

int main() {
    try {
        yk_can::VehicleConfig config = yk_can::VehicleConfig::from_json("config.example.json");
        yk_can::FourWheelVehicle car(config);
        car.connect();
        car.forward(0.15, 1.0);
        car.turn_left(0.15, 0.08, 1.0);
        car.turn_right(0.15, 0.08, 1.0);
        car.backward(0.15, 1.0);
        car.spin_left(0.12, 0.5);
        car.stop();
        car.close();
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << "\n";
        return 1;
    }
}
