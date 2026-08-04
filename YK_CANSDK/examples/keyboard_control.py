"""Windows keyboard demo: W/S/A/D, Space stop, Q quit.

Each key press refreshes the command watchdog. Releasing the keyboard and not
pressing another key stops the vehicle automatically within the configured
software watchdog interval.
"""

from __future__ import annotations

import msvcrt

from yk_can_sdk import FourWheelVehicle, VehicleConfig


def main() -> None:
    config = VehicleConfig.from_json("config.example.json")
    print("W前进 S后退 A左旋 D右旋 Space停车 Q退出")
    with FourWheelVehicle(config) as car:
        while True:
            key = msvcrt.getwch().lower()
            if key == "w":
                car.set_motion(0.15, 0.0)
            elif key == "s":
                car.set_motion(-0.15, 0.0)
            elif key == "a":
                car.set_motion(0.0, 0.12)
            elif key == "d":
                car.set_motion(0.0, -0.12)
            elif key == " ":
                car.stop()
            elif key == "q":
                car.emergency_stop("operator quit keyboard demo")
                break


if __name__ == "__main__":
    main()

