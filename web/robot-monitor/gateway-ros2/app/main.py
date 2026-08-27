"""EnzoPatrolLab gateway（rosbridge 版）。

与 0.2.0 前端完全兼容的 robot_status 消息结构：
  connections / connection_details / sensors / robot / pose / lidar

雷达数据源为 WSL 内 rosbridge 的 /scan（不再依赖 Windows COM 口）。
温湿度数据源为 Windows COM 口 LES11B（Modbus RTU）。
"""
from __future__ import annotations

import asyncio
import secrets
import socket
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .rosbridge import RosbridgeClient, parse_odometry, scan_to_points, scalar_value
from .serial_sensor import SerialTemperatureHumidityReader

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
        self.ros_connected = False
        self.usb_sensor_connected = False
        self.usb_sensor_detail = "正在检测温湿度传感器"
        self.chassis_connected = False
        self.chassis_detail = "正在检查底盘网络"
        self.lidar_connected = False
        self.lidar_scanning = False
        self.lidar_detail = "等待 rosbridge /scan 数据"
        self.lidar_rpm = 0.0
        self.lidar_points: list[list[float]] = []
        self.lidar_point_count = 0
        self.last_lidar_message_at = 0.0
        self.last_ros_message_at = 0.0
        self.last_data_message_at = 0.0
        self.has_real_data = False
        self.state: dict[str, Any] = {
            "sensors": {"temperature": None, "humidity": None, "noise": None},
            "robot": {"online": False, "taskStatus": "待命", "battery": None, "speed": 0.0},
            "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        }
        self.rosbridge = RosbridgeClient(self.on_ros_status, self.on_ros_message)
        self.serial_sensor = SerialTemperatureHumidityReader(
            self.on_usb_sensor_status, self.on_usb_sensor_reading)
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self.rosbridge.run(), name="rosbridge-client"),
            asyncio.create_task(self.serial_sensor.run(), name="serial-sensor"),
            asyncio.create_task(self.chassis_probe_loop(), name="chassis-probe"),
            asyncio.create_task(self.broadcast_loop(), name="frontend-broadcast"),
        ]

    async def stop(self) -> None:
        await self.rosbridge.stop()
        await self.serial_sensor.stop()
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
        await self.broadcast({
            "type": "bridge_status",
            "connected": connected,
            "rosbridge_url": settings.rosbridge_url,
            "timestamp": int(time.time() * 1000),
        })

    async def on_ros_message(self, topic: str, message: dict[str, Any]) -> None:
        now = time.time()
        async with self.state_lock:
            if topic == settings.lidar_topic:
                points = scan_to_points(message)
                self.lidar_points = points
                self.lidar_point_count = len(points)
                self.lidar_connected = True
                self.lidar_scanning = True
                self.lidar_detail = "rosbridge /scan 数据正常"
                self.last_lidar_message_at = now
                self.lidar_rpm = round(self.lidar_rpm + 0.5, 1) if self.lidar_rpm < 1 else self.lidar_rpm
                self.has_real_data = True
                self.state["robot"]["online"] = True
            elif topic == "/odom":
                pose, speed = parse_odometry(message)
                self.state["pose"].update(pose)
                self.state["robot"]["speed"] = round(speed, 3)
            elif topic == "/sensor/temperature":
                value = scalar_value(message)
                if value is not None:
                    self.state["sensors"]["temperature"] = round(value, 2)
            elif topic == "/sensor/humidity":
                value = scalar_value(message)
                if value is not None:
                    self.state["sensors"]["humidity"] = round(value, 2)
            elif topic == "/sensor/noise":
                value = scalar_value(message)
                if value is not None:
                    self.state["sensors"]["noise"] = round(value, 2)
            else:
                return
            self.last_ros_message_at = now
            self.has_real_data = True
            self.state["robot"]["online"] = True

    async def on_usb_sensor_status(self, connected: bool, detail: str) -> None:
        self.usb_sensor_connected = connected
        self.usb_sensor_detail = detail
        if connected:
            self.has_real_data = True

    async def on_usb_sensor_reading(self, temperature: float, humidity: float) -> None:
        now = time.time()
        async with self.state_lock:
            self.state["sensors"]["temperature"] = round(temperature, 2)
            self.state["sensors"]["humidity"] = round(humidity, 2)
        self.last_data_message_at = now
        self.has_real_data = True

    async def chassis_probe_loop(self) -> None:
        while True:
            connected = False
            detail = "底盘检测已禁用" if not settings.chassis_probe_enabled else f"{settings.chassis_host}:{settings.chassis_port} 不可达"
            if settings.chassis_probe_enabled:
                try:
                    sock = socket.create_connection(
                        (settings.chassis_host, settings.chassis_port), timeout=2)
                    sock.close()
                    connected = True
                    detail = f"{settings.chassis_host}:{settings.chassis_port} 网络可达"
                except OSError:
                    connected = False
            self.chassis_connected = connected
            self.chassis_detail = detail
            await asyncio.sleep(3.0)

    async def snapshot(self) -> dict[str, Any]:
        now = time.time()
        async with self.state_lock:
            if self.last_ros_message_at and now - self.last_ros_message_at > settings.stale_after_seconds:
                self.state["robot"]["online"] = False
            sensor_port = None
            if self.serial_sensor.active_port:
                sensor_port = self.serial_sensor.active_port
            serial_ports = []
            with suppress(Exception):
                from .serial_ports import serial_port_inventory
                serial_ports = [
                    {"device": info.device, "description": info.description}
                    for info in serial_port_inventory()
                ]
            return {
                "type": "robot_status",
                "timestamp": int(max(self.last_ros_message_at, self.last_data_message_at) * 1000),
                "source": "rosbridge",
                "has_real_data": self.has_real_data,
                "connections": {
                    "rosbridge": self.ros_connected,
                    "usb_sensor": self.usb_sensor_connected,
                    "chassis_gateway": self.chassis_connected,
                    "lidar_port": self.lidar_connected,
                    "lidar_scanning": self.lidar_scanning,
                },
                "connection_details": {
                    "usb_sensor": self.usb_sensor_detail,
                    "usb_sensor_port": sensor_port,
                    "chassis_gateway": self.chassis_detail,
                    "chassis_endpoint": f"{settings.chassis_host}:{settings.chassis_port}",
                    "lidar": self.lidar_detail,
                    "lidar_port": "rosbridge",
                    "rosbridge": "已连接" if self.ros_connected else "未连接",
                    "serial_ports": serial_ports,
                },
                "sensors": dict(self.state["sensors"]),
                "robot": dict(self.state["robot"]),
                "pose": dict(self.state["pose"]),
                "lidar": {
                    "connected": self.lidar_connected,
                    "scanning": self.lidar_scanning,
                    "port": "rosbridge",
                    "rpm": round(self.lidar_rpm, 1),
                    "point_count": self.lidar_point_count,
                    "timestamp": int(self.last_lidar_message_at * 1000),
                    "points": self.lidar_points,
                },
            }

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.clients_lock:
            self.clients.add(websocket)
        await websocket.send_json({
            "type": "bridge_status",
            "connected": self.ros_connected,
            "timestamp": int(time.time() * 1000),
        })
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


app = FastAPI(title="Robot Monitor Gateway", version="1.1.0", lifespan=lifespan)
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
    return {"items": [], "limit": limit}


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
                    supplied, settings.control_password)
                await websocket.send_json({
                    "type": "auth_result",
                    "ok": authorized,
                    "message": "控制权限已解锁" if authorized else "控制密码错误或网关尚未配置密码",
                })
                continue

            if request_type == "lock":
                authorized = False
                await websocket.send_json({"type": "auth_result", "ok": False, "message": "控制权限已锁定"})
                continue

            if request_type != "command" or request.get("command") not in COMMANDS:
                await websocket.send_json(
                    {"type": "command_result", "ok": False, "code": "bad_request", "message": "未知命令"})
                continue

            if not authorized:
                await websocket.send_json(
                    {"type": "command_result", "ok": False, "code": "unauthorized", "message": "请先解锁控制权限"})
                continue

            if not gateway.ros_connected:
                await websocket.send_json(
                    {"type": "command_result", "ok": False, "code": "bridge_offline", "message": "rosbridge 未连接，命令未发送"})
                continue

            command = request["command"]
            sent = await gateway.rosbridge.publish_command(command)
            await websocket.send_json({
                "type": "command_result",
                "ok": sent,
                "code": "published" if sent else "publish_failed",
                "message": f"已向 ROS2 提交「{COMMANDS[command]}」" if sent else "命令发送失败",
            })
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        await gateway.unregister(websocket)
