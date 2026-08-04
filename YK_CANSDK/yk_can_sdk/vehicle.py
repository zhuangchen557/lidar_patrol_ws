"""High-level four-wheel vehicle controller with fail-safe command refresh."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from .client import GatewayClient
from .config import VehicleConfig
from .protocol import DecodedFeedback, ThermalFaultFeedback


@dataclass(frozen=True, slots=True)
class WheelCommands:
    front_left: float = 0.0
    front_right: float = 0.0
    rear_left: float = 0.0
    rear_right: float = 0.0

    def is_zero(self, tolerance: float = 1e-9) -> bool:
        return all(
            abs(value) <= tolerance
            for value in (self.front_left, self.front_right, self.rear_left, self.rear_right)
        )


class FourWheelVehicle:
    """Controls front driver ID 1 and rear driver ID 2 by default.

    Public wheel commands use a vehicle-centric convention: positive means the
    wheel drives the vehicle forward. Direction signs are applied only when raw
    driver frames are sent.
    """

    def __init__(self, config: VehicleConfig | None = None, client: GatewayClient | None = None) -> None:
        self.config = config or VehicleConfig()
        self.client = client or GatewayClient(self.config.network)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._control_thread: threading.Thread | None = None
        self._target = WheelCommands()
        self._current = WheelCommands()
        self._last_command_at = time.monotonic()
        self._estop_latched = True
        self._estop_reason = "not connected"
        self.client.add_feedback_callback(self._on_feedback)

    @property
    def is_connected(self) -> bool:
        return self.client.is_connected

    @property
    def estop_latched(self) -> bool:
        with self._lock:
            return self._estop_latched

    @property
    def estop_reason(self) -> str | None:
        with self._lock:
            return self._estop_reason

    @property
    def current_commands(self) -> WheelCommands:
        with self._lock:
            return self._current

    def connect(self) -> None:
        """Connect, send the required ten zero commands per driver, then arm."""

        if self.is_connected:
            return
        self.client.connect()
        try:
            self._zero_burst(self.config.safety.unlock_repetitions)
        except Exception:
            self.client.close()
            raise
        with self._lock:
            self._target = WheelCommands()
            self._current = WheelCommands()
            self._last_command_at = time.monotonic()
            self._estop_latched = False
            self._estop_reason = None
        self._stop_event.clear()
        self._control_thread = threading.Thread(target=self._control_loop, name="yk-vehicle-control", daemon=True)
        self._control_thread.start()

    def close(self) -> None:
        """Immediately command zero repeatedly before closing the TCP socket."""

        with self._lock:
            self._estop_latched = True
            self._estop_reason = "controller closed"
            self._target = WheelCommands()
            self._current = WheelCommands()
        if self.is_connected:
            try:
                self._zero_burst(self.config.safety.stop_repetitions)
            except (ConnectionError, OSError):
                pass
        self._stop_event.set()
        if self._control_thread and self._control_thread is not threading.current_thread():
            self._control_thread.join(timeout=1.0)
        self._control_thread = None
        self.client.close()

    def set_motion(self, linear: float, angular: float) -> WheelCommands:
        """Set normalized chassis motion in [-1, 1]. Positive angular turns left."""

        if not -1.0 <= linear <= 1.0 or not -1.0 <= angular <= 1.0:
            raise ValueError("linear and angular must each be in -1.0..1.0")
        left = linear - angular
        right = linear + angular
        scale = max(1.0, abs(left), abs(right))
        maximum = self.config.safety.max_command
        return self.set_wheel_commands(left / scale * maximum, right / scale * maximum)

    def set_wheel_commands(self, left: float, right: float) -> WheelCommands:
        """Set equal front/rear logical wheel commands, bounded by max_command."""

        return self.set_axle_commands(left, right, left, right)

    def set_axle_commands(
        self, front_left: float, front_right: float, rear_left: float, rear_right: float
    ) -> WheelCommands:
        """Advanced four-wheel command; all values are logical vehicle directions."""

        command = WheelCommands(front_left, front_right, rear_left, rear_right)
        maximum = self.config.safety.max_command
        values = (command.front_left, command.front_right, command.rear_left, command.rear_right)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("wheel commands must be finite numbers")
        if any(abs(value) > maximum for value in values):
            raise ValueError(f"wheel command exceeds configured +/-{maximum} boundary")
        with self._lock:
            self._require_ready()
            self._target = command
            self._last_command_at = time.monotonic()
        return command

    def stop(self) -> None:
        """Immediate, non-latching stop. Future motion remains allowed."""

        with self._lock:
            self._target = WheelCommands()
            self._current = WheelCommands()
            self._last_command_at = time.monotonic()
        if self.is_connected:
            self._send_commands(WheelCommands())

    def smooth_stop(self, timeout_s: float = 1.0) -> None:
        """Decelerate using the configured rate, falling back to immediate stop."""

        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._lock:
            self._target = WheelCommands()
            self._last_command_at = time.monotonic()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.current_commands.is_zero(tolerance=0.5):
                return
            time.sleep(min(self.config.safety.command_period_s, 0.02))
        self.stop()

    def emergency_stop(self, reason: str = "manual emergency stop") -> None:
        """Latch motion inhibition and issue an immediate zero burst."""

        should_send = False
        with self._lock:
            if not self._estop_latched:
                should_send = True
            self._estop_latched = True
            self._estop_reason = reason
            self._target = WheelCommands()
            self._current = WheelCommands()
        if should_send and self.is_connected:
            try:
                self._zero_burst(min(3, self.config.safety.stop_repetitions))
            except (ConnectionError, OSError):
                pass

    def clear_emergency_stop(self) -> None:
        """Clear the latch only when both drivers report no active fault."""

        if not self.is_connected:
            raise ConnectionError("vehicle is not connected")
        for driver_id in (self.config.front_driver_id, self.config.rear_driver_id):
            telemetry = self.client.get_telemetry(driver_id)
            feedback = telemetry.thermal_fault if telemetry else None
            if feedback and feedback.has_fault:
                raise RuntimeError(f"driver {driver_id} still reports an active fault")
        self._zero_burst(self.config.safety.unlock_repetitions)
        with self._lock:
            self._estop_latched = False
            self._estop_reason = None
            self._last_command_at = time.monotonic()

    def move_for(self, linear: float, angular: float, duration_s: float) -> None:
        """Blocking bounded movement that refreshes the software watchdog."""

        if not 0 < duration_s <= self.config.safety.max_continuous_motion_s:
            raise ValueError(
                f"duration_s must be > 0 and <= {self.config.safety.max_continuous_motion_s}"
            )
        deadline = time.monotonic() + duration_s
        refresh = min(self.config.safety.command_watchdog_s / 2, 0.05)
        try:
            while time.monotonic() < deadline:
                self.set_motion(linear, angular)
                self._stop_event.wait(min(refresh, max(0.0, deadline - time.monotonic())))
        except BaseException:
            self.emergency_stop("move_for interrupted")
            raise
        finally:
            if not self.estop_latched:
                self.stop()

    def forward(self, speed: float = 0.2, duration_s: float = 1.0) -> None:
        self.move_for(abs(speed), 0.0, duration_s)

    def backward(self, speed: float = 0.2, duration_s: float = 1.0) -> None:
        self.move_for(-abs(speed), 0.0, duration_s)

    def turn_left(self, speed: float = 0.2, turn: float = 0.1, duration_s: float = 1.0) -> None:
        self.move_for(abs(speed), abs(turn), duration_s)

    def turn_right(self, speed: float = 0.2, turn: float = 0.1, duration_s: float = 1.0) -> None:
        self.move_for(abs(speed), -abs(turn), duration_s)

    def spin_left(self, speed: float = 0.2, duration_s: float = 1.0) -> None:
        self.move_for(0.0, abs(speed), duration_s)

    def spin_right(self, speed: float = 0.2, duration_s: float = 1.0) -> None:
        self.move_for(0.0, -abs(speed), duration_s)

    def get_logical_wheel_speeds(self) -> WheelCommands | None:
        """Return the latest speed feedback converted to vehicle-forward signs."""

        cfg = self.config
        front = self.client.get_telemetry(cfg.front_driver_id)
        rear = self.client.get_telemetry(cfg.rear_driver_id)
        if not front or not rear or not front.speed or not rear.speed:
            return None
        return WheelCommands(
            front.speed.motor1 * cfg.front_motor1_sign,
            front.speed.motor2 * cfg.front_motor2_sign,
            rear.speed.motor1 * cfg.rear_motor1_sign,
            rear.speed.motor2 * cfg.rear_motor2_sign,
        )

    def get_logical_wheel_positions(self) -> WheelCommands | None:
        """Return latest position counts converted to vehicle-forward signs."""

        cfg = self.config
        front = self.client.get_telemetry(cfg.front_driver_id)
        rear = self.client.get_telemetry(cfg.rear_driver_id)
        if not front or not rear or not front.position or not rear.position:
            return None
        return WheelCommands(
            front.position.motor1 * cfg.front_motor1_sign,
            front.position.motor2 * cfg.front_motor2_sign,
            rear.position.motor1 * cfg.rear_motor1_sign,
            rear.position.motor2 * cfg.rear_motor2_sign,
        )

    def _control_loop(self) -> None:
        period = self.config.safety.command_period_s
        next_tick = time.monotonic()
        while not self._stop_event.is_set():
            now = time.monotonic()
            with self._lock:
                stale = now - self._last_command_at > self.config.safety.command_watchdog_s
                desired = WheelCommands() if stale or self._estop_latched else self._target
                immediate = stale or self._estop_latched
                self._current = WheelCommands() if immediate else self._ramp(self._current, desired, period)
                command = self._current
            try:
                self._send_commands(command)
            except (ConnectionError, OSError) as exc:
                self.emergency_stop(f"network send failed: {exc}")
                self._stop_event.set()
                return
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay <= 0:
                next_tick = time.monotonic()
                continue
            self._stop_event.wait(delay)

    def _ramp(self, current: WheelCommands, target: WheelCommands, period: float) -> WheelCommands:
        def step(old: float, new: float) -> float:
            accelerating = abs(new) > abs(old) and old * new >= 0
            rate = (
                self.config.safety.max_acceleration_per_s
                if accelerating
                else self.config.safety.max_deceleration_per_s
            )
            delta = rate * period
            if new > old:
                return min(new, old + delta)
            return max(new, old - delta)

        return WheelCommands(
            step(current.front_left, target.front_left),
            step(current.front_right, target.front_right),
            step(current.rear_left, target.rear_left),
            step(current.rear_right, target.rear_right),
        )

    def _send_commands(self, command: WheelCommands) -> None:
        cfg = self.config
        self.client.send_motor_raw(
            cfg.front_driver_id,
            round(command.front_left) * cfg.front_motor1_sign,
            round(command.front_right) * cfg.front_motor2_sign,
        )
        self.client.send_motor_raw(
            cfg.rear_driver_id,
            round(command.rear_left) * cfg.rear_motor1_sign,
            round(command.rear_right) * cfg.rear_motor2_sign,
        )

    def _zero_burst(self, repetitions: int) -> None:
        for _ in range(repetitions):
            self._send_commands(WheelCommands())
            time.sleep(self.config.safety.command_period_s)

    def _on_feedback(self, feedback: DecodedFeedback) -> None:
        if (
            self.config.safety.auto_estop_on_fault
            and isinstance(feedback, ThermalFaultFeedback)
            and feedback.has_fault
        ):
            labels = feedback.motor1_faults.labels_zh + feedback.motor2_faults.labels_zh
            detail = ", ".join(labels) or (
                f"unknown bits m1=0x{int(feedback.motor1_faults):04X}, "
                f"m2=0x{int(feedback.motor2_faults):04X}"
            )
            self.emergency_stop(f"driver {feedback.driver_id} fault: {detail}")

    def _require_ready(self) -> None:
        if not self.is_connected:
            raise ConnectionError("vehicle is not connected")
        if self._estop_latched:
            raise RuntimeError(f"emergency stop is latched: {self._estop_reason}")

    def __enter__(self) -> "FourWheelVehicle":
        self.connect()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()
