"""Low-speed movement examples. Run only after the commissioning checklist."""

from yk_can_sdk import FourWheelVehicle, VehicleConfig


def main() -> None:
    config = VehicleConfig.from_json("config.example.json")
    with FourWheelVehicle(config) as car:
        car.forward(speed=0.15, duration_s=1.0)
        car.turn_left(speed=0.15, turn=0.08, duration_s=1.0)
        car.turn_right(speed=0.15, turn=0.08, duration_s=1.0)
        car.backward(speed=0.15, duration_s=1.0)
        car.spin_left(speed=0.12, duration_s=0.5)
        car.stop()


if __name__ == "__main__":
    main()

