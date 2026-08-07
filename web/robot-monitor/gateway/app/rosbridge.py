from __future__ import annotations

import asyncio
import json
import math
import time
from contextlib import suppress
from typing import Any, Awaitable, Callable

from websockets.asyncio.client import ClientConnection, connect

from .config import Settings

JsonObject = dict[str, Any]
StatusCallback = Callable[[bool], Awaitable[None]]
MessageCallback = Callable[[str, JsonObject], Awaitable[None]]


class RosbridgeClient:
    def __init__(
        self,
        config: Settings,
        on_status: StatusCallback,
        on_message: MessageCallback,
    ) -> None:
        self.config = config
        self.on_status = on_status
        self.on_message = on_message
        self.connected = False
        self._socket: ClientConnection | None = None
        self._send_lock = asyncio.Lock()
        self._stopping = False

    @property
    def subscriptions(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    self.config.temperature_topic,
                    self.config.humidity_topic,
                    self.config.temp_humidity_topic,
                    self.config.noise_topic,
                    self.config.odom_topic,
                    self.config.battery_topic,
                    self.config.mission_state_topic,
                )
            )
        )

    async def run(self) -> None:
        delay = 1.0
        while not self._stopping:
            try:
                async with connect(
                    self.config.rosbridge_url,
                    open_timeout=5,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=2**20,
                ) as socket:
                    self._socket = socket
                    self.connected = True
                    await self.on_status(True)
                    await self._subscribe_all()
                    await self._advertise_command_topic()
                    delay = 1.0
                    async for raw_message in socket:
                        await self._handle_raw_message(raw_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                self._socket = None
                if self.connected:
                    self.connected = False
                    await self.on_status(False)

            if not self._stopping:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15.0)

    async def stop(self) -> None:
        self._stopping = True
        if self._socket is not None:
            with suppress(Exception):
                await self._socket.close()

    async def _send(self, message: JsonObject) -> bool:
        socket = self._socket
        if socket is None or not self.connected:
            return False
        async with self._send_lock:
            await socket.send(json.dumps(message, ensure_ascii=False))
        return True

    async def _subscribe_all(self) -> None:
        for index, topic in enumerate(self.subscriptions):
            await self._send(
                {
                    "op": "subscribe",
                    "id": f"gateway-sub-{index}",
                    "topic": topic,
                    "throttle_rate": 200,
                    "queue_length": 1,
                }
            )

    async def _advertise_command_topic(self) -> None:
        await self._send(
            {
                "op": "advertise",
                "id": "gateway-command-advertise",
                "topic": self.config.command_topic,
                "type": "std_msgs/msg/String",
            }
        )

    async def _handle_raw_message(self, raw_message: str | bytes) -> None:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")
        try:
            payload = json.loads(raw_message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if payload.get("op") != "publish":
            return
        topic = payload.get("topic")
        message = payload.get("msg")
        if isinstance(topic, str) and isinstance(message, dict):
            await self.on_message(topic, message)

    async def publish_command(self, command: str) -> bool:
        return await self._send(
            {
                "op": "publish",
                "id": f"gateway-command-{time.time_ns()}",
                "topic": self.config.command_topic,
                "msg": {"data": command},
            }
        )


def scalar_value(message: JsonObject) -> float | None:
    value = message.get("data")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def quaternion_to_yaw(orientation: JsonObject) -> float:
    x = float(orientation.get("x", 0.0))
    y = float(orientation.get("y", 0.0))
    z = float(orientation.get("z", 0.0))
    w = float(orientation.get("w", 1.0))
    sin_yaw = 2.0 * (w * z + x * y)
    cos_yaw = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(sin_yaw, cos_yaw)


def parse_odometry(message: JsonObject) -> tuple[JsonObject, float]:
    pose = message.get("pose", {}).get("pose", {})
    position = pose.get("position", {})
    orientation = pose.get("orientation", {})
    twist = message.get("twist", {}).get("twist", {})
    linear = twist.get("linear", {})
    speed = math.hypot(float(linear.get("x", 0.0)), float(linear.get("y", 0.0)))
    return (
        {
            "x": float(position.get("x", 0.0)),
            "y": float(position.get("y", 0.0)),
            "yaw": quaternion_to_yaw(orientation),
        },
        speed,
    )
