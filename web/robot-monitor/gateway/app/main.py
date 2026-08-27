from __future__ import annotations

import asyncio
import secrets
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .history import HistoryRepository
from .rosbridge import RosbridgeClient, parse_odometry, scalar_value


COMMANDS = {
    "start_patrol": "开始巡检",
    "pause_patrol": "暂停巡检",
    "stop_patrol": "结束巡检",
    "emergency_stop": "紧急停止",
}


class RobotGateway:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.clients_lock = asyncio.Lock()
        self.state_lock = asyncio.Lock()
        self.history = HistoryRepository(settings.history_db)
        self.ros_connected = False
        self.last_ros_message_at = 0.0
        self.last_persisted_ros_message_at = 0.0
        self.has_real_data = False
        self.state: dict[str, Any] = {
            "sensors": {"temperature": None, "humidity": None, "noise": None},
            "robot": {
                "online": False,
                "taskStatus": "待命",
                "battery": None,
                "speed": 0.0,
            },
            "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        }
        self.rosbridge = RosbridgeClient(settings, self.on_ros_status, self.on_ros_message)
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        await self.history.initialize()
        self._tasks = [
            asyncio.create_task(self.rosbridge.run(), name="rosbridge-client"),
            asyncio.create_task(self.broadcast_loop(), name="frontend-broadcast"),
        ]

    async def stop(self) -> None:
        await self.rosbridge.stop()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task

    async def on_ros_status(self, connected: bool) -> None:
        self.ros_connected = connected
        if not connected:
            async with self.state_lock:
                self.state["robot"]["online"] = False
        await self.broadcast(
            {
                "type": "bridge_status",
                "connected": connected,
                "rosbridge_url": settings.rosbridge_url,
                "timestamp": int(time.time() * 1000),
            }
        )

    async def on_ros_message(self, topic: str, message: dict[str, Any]) -> None:
        now = time.time()
        async with self.state_lock:
            if topic == settings.temperature_topic:
                value = scalar_value(message)
                if value is not None:
                    self.state["sensors"]["temperature"] = round(value, 2)
            elif topic == settings.humidity_topic:
                value = scalar_value(message)
                if value is not None:
                    self.state["sensors"]["humidity"] = round(value, 2)
            elif topic == settings.temp_humidity_topic:
                if isinstance(message.get("temperature"), (int, float)):
                    self.state["sensors"]["temperature"] = round(float(message["temperature"]), 2)
                if isinstance(message.get("humidity"), (int, float)):
                    self.state["sensors"]["humidity"] = round(float(message["humidity"]), 2)
            elif topic == settings.noise_topic:
                value = scalar_value(message)
                if value is not None:
                    self.state["sensors"]["noise"] = round(value, 2)
            elif topic == settings.odom_topic:
                pose, speed = parse_odometry(message)
                self.state["pose"].update(pose)
                self.state["robot"]["speed"] = round(speed, 3)
            elif topic == settings.battery_topic:
                value = message.get("percentage", message.get("data"))
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = float(value)
                    self.state["robot"]["battery"] = round(value * 100 if 0 <= value <= 1 else value, 1)
            elif topic == settings.mission_state_topic:
                value = message.get("data")
                if isinstance(value, str) and value:
                    self.state["robot"]["taskStatus"] = value
            else:
                return

            self.last_ros_message_at = now
            self.has_real_data = True
            self.state["robot"]["online"] = True

    async def snapshot(self) -> dict[str, Any]:
        now = time.time()
        async with self.state_lock:
            if self.last_ros_message_at and now - self.last_ros_message_at > settings.stale_after_seconds:
                self.state["robot"]["online"] = False
            return {
                "type": "robot_status",
                "timestamp": int(self.last_ros_message_at * 1000) if self.last_ros_message_at else 0,
                "source": "rosbridge",
                "has_real_data": self.has_real_data,
                "sensors": dict(self.state["sensors"]),
                "robot": dict(self.state["robot"]),
                "pose": dict(self.state["pose"]),
            }

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.clients_lock:
            self.clients.add(websocket)
        await websocket.send_json(
            {
                "type": "bridge_status",
                "connected": self.ros_connected,
                "timestamp": int(time.time() * 1000),
            }
        )
        await websocket.send_json(await self.snapshot())

    async def unregister(self, websocket: WebSocket) -> None:
        async with self.clients_lock:
            self.clients.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self.clients_lock:
            clients = tuple(self.clients)
        disconnected: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:
                disconnected.append(client)
        if disconnected:
            async with self.clients_lock:
                for client in disconnected:
                    self.clients.discard(client)

    async def broadcast_loop(self) -> None:
        while True:
            payload = await self.snapshot()
            if self.last_ros_message_at > self.last_persisted_ros_message_at:
                await self.history.append(payload)
                self.last_persisted_ros_message_at = self.last_ros_message_at
            await self.broadcast(payload)
            await asyncio.sleep(settings.broadcast_interval_seconds)


gateway = RobotGateway()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await gateway.start()
    try:
        yield
    finally:
        await gateway.stop()


app = FastAPI(title="Robot Monitor Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "gateway": "online",
        "rosbridge_connected": gateway.ros_connected,
        "has_real_data": gateway.has_real_data,
        "control_auth_configured": bool(settings.control_password),
    }


@app.get("/api/history")
async def history(limit: int = Query(default=60, ge=1, le=1000)) -> dict[str, Any]:
    return {"items": await gateway.history.latest(limit), "limit": limit}


@app.websocket("/ws/robot")
async def robot_stream(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin and "*" not in settings.allowed_origins and origin not in settings.allowed_origins:
        await websocket.close(code=1008, reason="Origin is not allowed")
        return
    await gateway.register(websocket)
    authorized = False
    try:
        while True:
            request = await websocket.receive_json()
            request_type = request.get("type")

            if request_type == "auth":
                supplied = request.get("password", "")
                authorized = bool(settings.control_password) and isinstance(supplied, str) and secrets.compare_digest(
                    supplied,
                    settings.control_password,
                )
                await websocket.send_json(
                    {
                        "type": "auth_result",
                        "ok": authorized,
                        "message": "控制权限已解锁" if authorized else "控制密码错误或网关尚未配置密码",
                    }
                )
                continue

            if request_type == "lock":
                authorized = False
                await websocket.send_json({"type": "auth_result", "ok": False, "message": "控制权限已锁定"})
                continue

            if request_type != "command" or request.get("command") not in COMMANDS:
                await websocket.send_json(
                    {"type": "command_result", "ok": False, "code": "bad_request", "message": "未知命令"}
                )
                continue

            if not authorized:
                await websocket.send_json(
                    {"type": "command_result", "ok": False, "code": "unauthorized", "message": "请先解锁控制权限"}
                )
                continue

            if not gateway.ros_connected:
                await websocket.send_json(
                    {"type": "command_result", "ok": False, "code": "bridge_offline", "message": "rosbridge 未连接，命令未发送"}
                )
                continue

            command = request["command"]
            sent = await gateway.rosbridge.publish_command(command)
            await websocket.send_json(
                {
                    "type": "command_result",
                    "ok": sent,
                    "code": "published" if sent else "publish_failed",
                    "message": f"已向 ROS2 提交“{COMMANDS[command]}”" if sent else "命令发送失败",
                }
            )
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        await gateway.unregister(websocket)
