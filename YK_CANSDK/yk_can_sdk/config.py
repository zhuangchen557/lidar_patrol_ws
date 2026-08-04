"""Validated SDK configuration with conservative movement defaults."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    """USR-CAN115 TCP Server endpoint."""

    host: str = "192.168.0.7"
    port: int = 5578
    connect_timeout_s: float = 5.0
    receive_timeout_s: float = 0.2

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be in 1..65535")
        if self.connect_timeout_s <= 0 or self.receive_timeout_s <= 0:
            raise ValueError("socket timeouts must be positive")


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    """Software movement boundaries.

    The driver manual allows open-loop commands in -1100..1100.  The SDK uses
    +/-300 by default so first commissioning is deliberately conservative.
    """

    max_command: int = 300
    command_period_s: float = 0.02
    command_watchdog_s: float = 0.25
    max_acceleration_per_s: float = 600.0
    max_deceleration_per_s: float = 1200.0
    max_continuous_motion_s: float = 10.0
    unlock_repetitions: int = 10
    stop_repetitions: int = 10
    auto_estop_on_fault: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.max_command <= 1100:
            raise ValueError("max_command must be in 1..1100 for open-loop mode")
        if not 0.01 <= self.command_period_s <= 0.1:
            raise ValueError("command_period_s must be in 0.01..0.1 seconds")
        if not self.command_period_s < self.command_watchdog_s < 0.5:
            raise ValueError("command_watchdog_s must be greater than the period and below 0.5 s")
        if self.max_acceleration_per_s <= 0 or self.max_deceleration_per_s <= 0:
            raise ValueError("acceleration and deceleration limits must be positive")
        if self.max_continuous_motion_s <= 0:
            raise ValueError("max_continuous_motion_s must be positive")
        if not 10 <= self.unlock_repetitions <= 100:
            raise ValueError("unlock_repetitions must be in 10..100")
        if not 1 <= self.stop_repetitions <= 100:
            raise ValueError("stop_repetitions must be in 1..100")


@dataclass(frozen=True, slots=True)
class VehicleConfig:
    """Two-driver topology and wheel direction mapping.

    Each axle uses motor 1 as the left wheel and motor 2 as the right wheel.
    The supplied commissioning workbook records motor 2 as physically reversed,
    therefore its default sign is -1 on both drivers.
    """

    network: NetworkConfig = field(default_factory=NetworkConfig)
    safety: SafetyLimits = field(default_factory=SafetyLimits)
    front_driver_id: int = 1
    rear_driver_id: int = 2
    front_motor1_sign: int = 1
    front_motor2_sign: int = -1
    rear_motor1_sign: int = 1
    rear_motor2_sign: int = -1

    def __post_init__(self) -> None:
        ids = (self.front_driver_id, self.rear_driver_id)
        if any(not 1 <= item <= 100 for item in ids):
            raise ValueError("driver IDs must be in 1..100")
        if self.front_driver_id == self.rear_driver_id:
            raise ValueError("front and rear driver IDs must be different")
        signs = (
            self.front_motor1_sign,
            self.front_motor2_sign,
            self.rear_motor1_sign,
            self.rear_motor2_sign,
        )
        if any(sign not in (-1, 1) for sign in signs):
            raise ValueError("motor direction signs must be +1 or -1")

    @classmethod
    def from_json(cls, path: str | Path) -> "VehicleConfig":
        data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        network = NetworkConfig(**data.pop("network", {}))
        safety = SafetyLimits(**data.pop("safety", {}))
        return cls(network=network, safety=safety, **data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

