"""Keep both drivers stopped and print parsed feedback."""

from __future__ import annotations

import time

from yk_can_sdk import FourWheelVehicle, VehicleConfig


def main() -> None:
    config = VehicleConfig.from_json("config.example.json")
    with FourWheelVehicle(config) as car:
        print("Connected. Press Ctrl+C to exit; zero commands continue at 50 Hz.")
        try:
            while True:
                for driver_id in (config.front_driver_id, config.rear_driver_id):
                    print(car.client.get_telemetry(driver_id))
                time.sleep(0.5)
        except KeyboardInterrupt:
            car.emergency_stop("operator pressed Ctrl+C")


if __name__ == "__main__":
    main()

