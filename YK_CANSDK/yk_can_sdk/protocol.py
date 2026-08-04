"""USR-CAN115 13-byte standard conversion and Yunkang CAN protocol."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntFlag
from typing import TypeAlias


GATEWAY_FRAME_SIZE = 13
YK_CAN_ID_PREFIX = 0x0DEE
KNOWN_FUNCTIONS = frozenset({0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0A, 0x0B})


@dataclass(frozen=True, slots=True)
class CanFrame:
    """One classic CAN frame represented in CAN115 standard-conversion form."""

    can_id: int
    data: bytes = b""
    extended: bool = True
    remote: bool = False

    def __post_init__(self) -> None:
        max_id = 0x1FFFFFFF if self.extended else 0x7FF
        if not 0 <= self.can_id <= max_id:
            raise ValueError(f"CAN ID out of range for frame type: 0x{self.can_id:X}")
        if len(self.data) > 8:
            raise ValueError("classic CAN payload cannot exceed 8 bytes")

    @property
    def dlc(self) -> int:
        return len(self.data)

    @property
    def driver_id(self) -> int | None:
        if (self.can_id >> 16) != YK_CAN_ID_PREFIX:
            return None
        return (self.can_id >> 8) & 0xFF

    @property
    def function(self) -> int | None:
        return self.can_id & 0xFF if self.driver_id is not None else None

    def to_gateway_bytes(self) -> bytes:
        frame_info = (0x80 if self.extended else 0) | (0x40 if self.remote else 0) | self.dlc
        return bytes([frame_info]) + self.can_id.to_bytes(4, "big") + self.data.ljust(8, b"\x00")

    @classmethod
    def from_gateway_bytes(cls, packet: bytes, *, require_yk_frame: bool = False) -> "CanFrame":
        if len(packet) != GATEWAY_FRAME_SIZE:
            raise ValueError("CAN115 standard-conversion packet must be exactly 13 bytes")
        info = packet[0]
        if info & 0x30:
            raise ValueError("reserved frame-info bits must be zero")
        dlc = info & 0x0F
        if dlc > 8:
            raise ValueError("CAN DLC cannot exceed 8")
        frame = cls(
            can_id=int.from_bytes(packet[1:5], "big"),
            data=bytes(packet[5 : 5 + dlc]),
            extended=bool(info & 0x80),
            remote=bool(info & 0x40),
        )
        if require_yk_frame and not is_plausible_yk_frame(frame):
            raise ValueError("packet is not a plausible Yunkang extended CAN frame")
        return frame


def is_plausible_yk_frame(frame: CanFrame) -> bool:
    return (
        frame.extended
        and not frame.remote
        and (frame.can_id >> 16) == YK_CAN_ID_PREFIX
        and frame.driver_id is not None
        and 1 <= frame.driver_id <= 0xFF
        and frame.function in KNOWN_FUNCTIONS
    )


class CanStreamParser:
    """Resynchronizing parser for TCP fragmentation, coalescing, and stray bytes."""

    def __init__(self, *, yk_frames_only: bool = True) -> None:
        self._buffer = bytearray()
        self.yk_frames_only = yk_frames_only
        self.discarded_bytes = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[CanFrame]:
        self._buffer.extend(chunk)
        frames: list[CanFrame] = []
        while len(self._buffer) >= GATEWAY_FRAME_SIZE:
            packet = bytes(self._buffer[:GATEWAY_FRAME_SIZE])
            try:
                frame = CanFrame.from_gateway_bytes(packet, require_yk_frame=self.yk_frames_only)
            except ValueError:
                del self._buffer[0]
                self.discarded_bytes += 1
                continue
            del self._buffer[:GATEWAY_FRAME_SIZE]
            frames.append(frame)
        return frames

    def clear(self) -> None:
        self._buffer.clear()


def yk_can_id(driver_id: int, function: int) -> int:
    if not 1 <= driver_id <= 100:
        raise ValueError("driver_id must be in 1..100")
    if not 0 <= function <= 0xFF:
        raise ValueError("function must be in 0..255")
    return (YK_CAN_ID_PREFIX << 16) | (driver_id << 8) | function


def build_motor_frame(driver_id: int, motor1: int, motor2: int) -> CanFrame:
    """Build function 0x00. Values are raw driver values, not logical wheel directions."""

    for name, value in (("motor1", motor1), ("motor2", motor2)):
        if not -(2**31) <= value < 2**31:
            raise ValueError(f"{name} must fit a signed 32-bit integer")
    return CanFrame(yk_can_id(driver_id, 0x00), struct.pack(">ii", motor1, motor2))


def build_parameter_write_frame(driver_id: int, register: int, value: int) -> CanFrame:
    """Build firmware V1.221+ function 0x0A parameter write command."""

    if register in (0x0026, 0x0027):
        raise ValueError("registers 0x0026 and 0x0027 are forbidden by the driver manual")
    if not 0 <= register <= 0xFFFF or not 0 <= value <= 0xFFFF:
        raise ValueError("register and value must fit unsigned 16-bit integers")
    data = bytes([0x83]) + register.to_bytes(2, "big") + b"\x00" + value.to_bytes(2, "big") + b"\x00\x00"
    return CanFrame(yk_can_id(driver_id, 0x0A), data)


class Fault(IntFlag):
    NONE = 0
    OVERCURRENT = 1 << 0
    LOAD_ABNORMAL = 1 << 1
    OVERTEMPERATURE = 1 << 2
    OVERVOLTAGE = 1 << 3
    UNDERVOLTAGE = 1 << 4
    STALL = 1 << 5
    HALL_ABNORMAL = 1 << 6
    ABNORMAL_JITTER = 1 << 7

    @property
    def labels_zh(self) -> tuple[str, ...]:
        labels = {
            Fault.OVERCURRENT: "电流过大",
            Fault.LOAD_ABNORMAL: "负载异常",
            Fault.OVERTEMPERATURE: "温度过高",
            Fault.OVERVOLTAGE: "电压过高",
            Fault.UNDERVOLTAGE: "电压过低",
            Fault.STALL: "堵转",
            Fault.HALL_ABNORMAL: "霍尔异常",
            Fault.ABNORMAL_JITTER: "异常抖动",
        }
        return tuple(label for flag, label in labels.items() if self & flag)


@dataclass(frozen=True, slots=True)
class FeedbackBase:
    driver_id: int
    received_monotonic: float


@dataclass(frozen=True, slots=True)
class SpeedFeedback(FeedbackBase):
    motor1: int
    motor2: int


@dataclass(frozen=True, slots=True)
class ElectricalFeedback(FeedbackBase):
    motor1_current_a: float
    motor2_current_a: float
    supply_voltage_v: float
    tail: bytes


@dataclass(frozen=True, slots=True)
class ThermalFaultFeedback(FeedbackBase):
    motor1_temperature_c: float
    motor2_temperature_c: float
    motor1_faults: Fault
    motor2_faults: Fault

    @property
    def has_fault(self) -> bool:
        return bool(self.motor1_faults or self.motor2_faults)


@dataclass(frozen=True, slots=True)
class PositionFeedback(FeedbackBase):
    motor1: int
    motor2: int


@dataclass(frozen=True, slots=True)
class ParameterAck(FeedbackBase):
    command: int
    register: int
    value: int
    reserved: bytes


@dataclass(frozen=True, slots=True)
class RawFeedback(FeedbackBase):
    function: int
    data: bytes


DecodedFeedback: TypeAlias = (
    SpeedFeedback | ElectricalFeedback | ThermalFaultFeedback | PositionFeedback | ParameterAck | RawFeedback
)


def _require_eight(frame: CanFrame) -> bytes:
    if len(frame.data) != 8:
        raise ValueError(f"function 0x{frame.function:02X} requires an 8-byte payload")
    return frame.data


def decode_feedback(frame: CanFrame, *, received_monotonic: float = 0.0) -> DecodedFeedback:
    """Decode documented driver-to-host functions 0x01..0x04 and 0x0B."""

    if not is_plausible_yk_frame(frame) or frame.driver_id is None or frame.function is None:
        raise ValueError("not a Yunkang driver frame")
    driver_id = frame.driver_id
    function = frame.function
    if function == 0x01:
        motor1, motor2 = struct.unpack(">ii", _require_eight(frame))
        return SpeedFeedback(driver_id, received_monotonic, motor1, motor2)
    if function == 0x02:
        current1, current2, voltage = struct.unpack(">hhh", _require_eight(frame)[:6])
        return ElectricalFeedback(
            driver_id,
            received_monotonic,
            current1 / 10.0,
            current2 / 10.0,
            voltage / 10.0,
            frame.data[6:8],
        )
    if function == 0x03:
        temp1, temp2, faults1, faults2 = struct.unpack(">hhHH", _require_eight(frame))
        return ThermalFaultFeedback(
            driver_id,
            received_monotonic,
            temp1 / 10.0,
            temp2 / 10.0,
            Fault(faults1),
            Fault(faults2),
        )
    if function == 0x04:
        motor1, motor2 = struct.unpack(">ii", _require_eight(frame))
        return PositionFeedback(driver_id, received_monotonic, motor1, motor2)
    if function == 0x0B:
        data = _require_eight(frame)
        return ParameterAck(
            driver_id,
            received_monotonic,
            data[0],
            int.from_bytes(data[1:3], "big"),
            int.from_bytes(data[4:6], "big"),
            bytes([data[3]]) + data[6:8],
        )
    return RawFeedback(driver_id, received_monotonic, function, frame.data)

