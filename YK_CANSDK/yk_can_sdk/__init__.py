"""Public API for the YK CAN four-wheel vehicle SDK."""

from .config import NetworkConfig, SafetyLimits, VehicleConfig
from .client import GatewayClient, DriverTelemetry
from .protocol import (
    CanFrame,
    CanStreamParser,
    ElectricalFeedback,
    Fault,
    ParameterAck,
    PositionFeedback,
    RawFeedback,
    SpeedFeedback,
    ThermalFaultFeedback,
    build_motor_frame,
    build_parameter_write_frame,
    decode_feedback,
)
from .vehicle import FourWheelVehicle, WheelCommands

__all__ = [
    "CanFrame",
    "CanStreamParser",
    "DriverTelemetry",
    "ElectricalFeedback",
    "Fault",
    "FourWheelVehicle",
    "GatewayClient",
    "NetworkConfig",
    "ParameterAck",
    "PositionFeedback",
    "RawFeedback",
    "SafetyLimits",
    "SpeedFeedback",
    "ThermalFaultFeedback",
    "VehicleConfig",
    "WheelCommands",
    "build_motor_frame",
    "build_parameter_write_frame",
    "decode_feedback",
]

__version__ = "0.1.0"

