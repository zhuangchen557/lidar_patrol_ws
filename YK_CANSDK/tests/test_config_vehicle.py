from __future__ import annotations

import unittest

from yk_can_sdk import NetworkConfig, SafetyLimits, VehicleConfig, WheelCommands
from yk_can_sdk.vehicle import FourWheelVehicle


class FakeClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.sent: list[tuple[int, int, int]] = []
        self.callbacks = []

    def add_feedback_callback(self, callback):
        self.callbacks.append(callback)

    def send_motor_raw(self, driver_id: int, motor1: int, motor2: int) -> None:
        self.sent.append((driver_id, motor1, motor2))

    def get_telemetry(self, _driver_id: int):
        return None

    def close(self) -> None:
        self.is_connected = False


class ConfigAndVehicleTests(unittest.TestCase):
    def test_defaults_match_user_endpoint(self) -> None:
        network = NetworkConfig()
        self.assertEqual((network.host, network.port), ("192.168.0.7", 5578))

    def test_safety_boundaries(self) -> None:
        with self.assertRaises(ValueError):
            SafetyLimits(max_command=1101)
        with self.assertRaises(ValueError):
            SafetyLimits(command_watchdog_s=0.5)
        with self.assertRaises(ValueError):
            VehicleConfig(front_driver_id=1, rear_driver_id=1)

    def test_direction_mapping(self) -> None:
        fake = FakeClient()
        vehicle = FourWheelVehicle(client=fake)  # type: ignore[arg-type]
        vehicle._send_commands(WheelCommands(100, 100, 100, 100))
        self.assertEqual(fake.sent, [(1, 100, -100), (2, 100, -100)])

    def test_mixing_and_bounds(self) -> None:
        fake = FakeClient()
        vehicle = FourWheelVehicle(client=fake)  # type: ignore[arg-type]
        vehicle._estop_latched = False
        straight = vehicle.set_motion(0.5, 0.0)
        self.assertEqual(straight, WheelCommands(150, 150, 150, 150))
        spin_left = vehicle.set_motion(0.0, 1.0)
        self.assertEqual(spin_left, WheelCommands(-300, 300, -300, 300))
        with self.assertRaises(ValueError):
            vehicle.set_axle_commands(301, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()

