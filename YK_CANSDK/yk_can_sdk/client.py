"""Thread-safe TCP client for a CAN115 configured as TCP Server."""

from __future__ import annotations

import copy
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .config import NetworkConfig
from .protocol import (
    CanFrame,
    CanStreamParser,
    DecodedFeedback,
    ElectricalFeedback,
    ParameterAck,
    PositionFeedback,
    SpeedFeedback,
    ThermalFaultFeedback,
    build_motor_frame,
    decode_feedback,
)


FeedbackCallback = Callable[[DecodedFeedback], None]


@dataclass(slots=True)
class DriverTelemetry:
    driver_id: int
    speed: SpeedFeedback | None = None
    electrical: ElectricalFeedback | None = None
    thermal_fault: ThermalFaultFeedback | None = None
    position: PositionFeedback | None = None
    parameter_ack: ParameterAck | None = None

    @property
    def last_update_monotonic(self) -> float | None:
        updates = [
            item.received_monotonic
            for item in (self.speed, self.electrical, self.thermal_fault, self.position, self.parameter_ack)
            if item is not None
        ]
        return max(updates) if updates else None


class GatewayClient:
    """Owns the TCP connection, receive thread, parser, and telemetry cache."""

    def __init__(self, config: NetworkConfig | None = None) -> None:
        self.config = config or NetworkConfig()
        self._socket: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._connected = threading.Event()
        self._receiver: threading.Thread | None = None
        self._callbacks: list[FeedbackCallback] = []
        self._telemetry: dict[int, DriverTelemetry] = {}
        self._last_error: BaseException | None = None
        self.parser = CanStreamParser(yk_frames_only=True)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def last_error(self) -> BaseException | None:
        with self._state_lock:
            return self._last_error

    def connect(self) -> None:
        if self.is_connected:
            return
        sock = socket.create_connection(
            (self.config.host, self.config.port), timeout=self.config.connect_timeout_s
        )
        sock.settimeout(self.config.receive_timeout_s)
        with self._state_lock:
            self._socket = sock
            self._last_error = None
            self.parser.clear()
        self._stop_event.clear()
        self._connected.set()
        self._receiver = threading.Thread(target=self._receive_loop, name="can115-receiver", daemon=True)
        self._receiver.start()

    def close(self) -> None:
        self._stop_event.set()
        self._connected.clear()
        with self._state_lock:
            sock, self._socket = self._socket, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        if self._receiver and self._receiver is not threading.current_thread():
            self._receiver.join(timeout=1.0)
        self._receiver = None

    def add_feedback_callback(self, callback: FeedbackCallback) -> None:
        with self._state_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def remove_feedback_callback(self, callback: FeedbackCallback) -> None:
        with self._state_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def send_frame(self, frame: CanFrame) -> None:
        packet = frame.to_gateway_bytes()
        with self._send_lock:
            sock = self._socket
            if sock is None or not self.is_connected:
                raise ConnectionError("CAN115 TCP client is not connected")
            try:
                sock.sendall(packet)
            except OSError as exc:
                self._record_error(exc)
                raise ConnectionError("failed to send to CAN115") from exc

    def send_motor_raw(self, driver_id: int, motor1: int, motor2: int) -> None:
        self.send_frame(build_motor_frame(driver_id, motor1, motor2))

    def get_telemetry(self, driver_id: int) -> DriverTelemetry | None:
        with self._state_lock:
            item = self._telemetry.get(driver_id)
            return copy.deepcopy(item) if item is not None else None

    def wait_for_feedback(self, driver_id: int, timeout_s: float = 1.0) -> DriverTelemetry | None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            telemetry = self.get_telemetry(driver_id)
            if telemetry and telemetry.last_update_monotonic is not None:
                return telemetry
            if self._stop_event.wait(0.01):
                break
        return None

    def _receive_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                sock = self._socket
                if sock is None:
                    return
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    raise ConnectionError("CAN115 closed the TCP connection")
                now = time.monotonic()
                for frame in self.parser.feed(chunk):
                    try:
                        feedback = decode_feedback(frame, received_monotonic=now)
                    except ValueError:
                        continue
                    self._store_feedback(feedback)
        except (OSError, ConnectionError) as exc:
            if not self._stop_event.is_set():
                self._record_error(exc)
        finally:
            self._connected.clear()
            with self._state_lock:
                sock, self._socket = self._socket, None
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

    def _store_feedback(self, feedback: DecodedFeedback) -> None:
        with self._state_lock:
            telemetry = self._telemetry.setdefault(feedback.driver_id, DriverTelemetry(feedback.driver_id))
            if isinstance(feedback, SpeedFeedback):
                telemetry.speed = feedback
            elif isinstance(feedback, ElectricalFeedback):
                telemetry.electrical = feedback
            elif isinstance(feedback, ThermalFaultFeedback):
                telemetry.thermal_fault = feedback
            elif isinstance(feedback, PositionFeedback):
                telemetry.position = feedback
            elif isinstance(feedback, ParameterAck):
                telemetry.parameter_ack = feedback
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            try:
                callback(feedback)
            except Exception:
                # User callbacks must never kill the receive thread.
                continue

    def _record_error(self, exc: BaseException) -> None:
        with self._state_lock:
            self._last_error = exc
        self._connected.clear()

    def __enter__(self) -> "GatewayClient":
        self.connect()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()
