"""rosbridge WebSocket 客户端：订阅 /scan /odom /sensor/* 并解析，支持发布命令。

数据源：WSL 内 rosbridge_server（ws://127.0.0.1:9090，mirrored 模式与 Windows 回环互通）。
雷达 /scan 由 WSL 侧 scan_repub 以 RELIABLE QoS 转发（LD19 原生 BEST_EFFORT 订阅不到）。
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Awaitable, Callable

from .config import settings

StatusCallback = Callable[[bool], Awaitable[None]]
MessageCallback = Callable[[str, dict[str, Any]], Awaitable[None]]

COMMAND_TOPIC = "/cmd_vel"
COMMANDS = {
    "start_patrol": "开始巡检",
    "pause_patrol": "暂停巡检",
    "stop_patrol": "结束巡检",
    "emergency_stop": "紧急停止",
}

SCAN_TOPIC = "/scan"
ODOM_TOPIC = "/odom"


def scalar_value(message: dict[str, Any]) -> float | None:
    for key in ("data", "value", "temperature", "humidity"):
        value = message.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def parse_odometry(message: dict[str, Any]) -> tuple[dict[str, float], float]:
    pose = message.get("pose", {}).get("pose", message)
    pos = pose.get("position", {})
    orient = pose.get("orientation", {})
    x = pos.get("x", 0.0)
    y = pos.get("y", 0.0)
    sin = orient.get("z", 0.0)
    cos = orient.get("w", 1.0)
    yaw = math.atan2(2 * (sin * cos), 1 - 2 * sin * sin)
    speed = 0.0
    twist = message.get("twist", {}).get("twist", {})
    linear = twist.get("linear", {})
    speed = abs(linear.get("x", 0.0))
    return {"x": float(x), "y": float(y), "yaw": yaw}, float(speed)


def scan_to_points(message: dict[str, Any]) -> list[list[float]]:
    """LaserScan -> [[x, y, intensity], ...] 车体系笛卡尔坐标。"""
    ranges = message.get("ranges", [])
    angle_min = message.get("angle_min", 0.0)
    angle_increment = message.get("angle_increment", 0.0)
    intensities = message.get("intensities", []) or []
    points: list[list[float]] = []
    for i, distance in enumerate(ranges):
        if not isinstance(distance, (int, float)) or math.isnan(distance) or math.isinf(distance):
            continue
        if distance <= 0.05:
            continue
        angle = angle_min + i * angle_increment
        x = distance * math.cos(angle)
        y = distance * math.sin(angle)
        intensity = 0
        if i < len(intensities) and isinstance(intensities[i], (int, float)):
            intensity = int(intensities[i])
        points.append([round(x, 3), round(y, 3), intensity])
    return points


class RosbridgeClient:
    def __init__(self, on_status: StatusCallback, on_message: MessageCallback) -> None:
        self.on_status = on_status
        self.on_message = on_message
        self._ws = None
        self._running = False
        self.connected = False
        self._subscribed_topics: set[str] = set()
        self._lock = asyncio.Lock()

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._connect_and_spin()
            except Exception:
                pass
            if not self._running:
                break
            await asyncio.sleep(settings.rosbridge_reconnect_delay)

    async def stop(self) -> None:
        self._running = False
        ws = self._ws
        self._ws = None
        if ws is not None:
            with __import__("contextlib").suppress(Exception):
                await ws.close()
        self.connected = False

    async def _connect_and_spin(self) -> None:
        import websockets
        ws = await websockets.connect(settings.rosbridge_url, ping_interval=20, ping_timeout=10)
        self._ws = ws
        self.connected = True
        await self.on_status(True)
        self._subscribed_topics.clear()
        for topic in (SCAN_TOPIC, ODOM_TOPIC, "/sensor/temperature", "/sensor/humidity", "/sensor/noise"):
            try:
                await ws.send(json.dumps({"op": "subscribe", "topic": topic}))
                self._subscribed_topics.add(topic)
            except Exception:
                pass
        try:
            async for raw in ws:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                topic = message.get("topic")
                if message.get("op") == "publish" and topic:
                    await self.on_message(topic, message.get("msg", {}))
        finally:
            self.connected = False
            self._ws = None
            await self.on_status(False)

    async def publish_command(self, command: str) -> bool:
        import websockets
        if not self.connected or self._ws is None:
            return False
        try:
            if command == "emergency_stop":
                payload = {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}
            elif command == "start_patrol":
                payload = {"linear": {"x": 0.2, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}
            elif command == "pause_patrol":
                payload = {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}
            elif command == "stop_patrol":
                payload = {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}
            else:
                return False
            await self._ws.send(json.dumps({
                "op": "publish",
                "topic": COMMAND_TOPIC,
                "msg": payload,
            }))
            return True
        except Exception:
            return False
