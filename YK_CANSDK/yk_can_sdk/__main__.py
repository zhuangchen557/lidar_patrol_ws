"""Small safe-by-default command-line interface for Windows commissioning."""

from __future__ import annotations

import argparse
import json
import time

from .config import NetworkConfig, SafetyLimits, VehicleConfig
from .vehicle import FourWheelVehicle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control/inspect a Yunkang two-driver vehicle through CAN115")
    parser.add_argument("--host", default="192.168.0.7", help="CAN115 IP address")
    parser.add_argument("--port", type=int, default=5578, help="CAN115 TCP Server local port")
    parser.add_argument("--max-command", type=int, default=300, help="software command boundary (1..1100)")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="send safe zero commands and print feedback")
    status.add_argument("--seconds", type=float, default=2.0)

    move = sub.add_parser("move", help="perform one bounded movement")
    move.add_argument("--linear", type=float, required=True)
    move.add_argument("--angular", type=float, default=0.0)
    move.add_argument("--duration", type=float, required=True)
    move.add_argument("--arm", action="store_true", help="required acknowledgement that wheels are safe to move")
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = VehicleConfig(
        network=NetworkConfig(args.host, args.port),
        safety=SafetyLimits(max_command=args.max_command),
    )
    if args.command == "move" and not args.arm:
        raise SystemExit("Refusing movement without --arm. Lift wheels and prepare an emergency stop first.")

    with FourWheelVehicle(config) as vehicle:
        if args.command == "move":
            vehicle.move_for(args.linear, args.angular, args.duration)
            return 0
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            data = {}
            for driver_id in (config.front_driver_id, config.rear_driver_id):
                telemetry = vehicle.client.get_telemetry(driver_id)
                data[str(driver_id)] = repr(telemetry) if telemetry else None
            print(json.dumps(data, ensure_ascii=False, indent=2))
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

