"""EnzoPatrolLab gateway（rosbridge 版）配置，环境变量与 0.2.0 main.cjs 对齐。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _csv(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8000
    allowed_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173", "file://", "null",
    ])
    rosbridge_url: str = "ws://127.0.0.1:9090"
    rosbridge_reconnect_delay: float = 2.0
    stale_after_seconds: float = 5.0
    broadcast_interval_seconds: float = 1.0

    usb_sensor_port: str = ""
    usb_sensor_auto_detect: bool = True
    usb_sensor_baudrate: int = 9600
    usb_sensor_slave_id: int = 1

    chassis_probe_enabled: bool = True
    chassis_host: str = "192.168.0.7"
    chassis_port: int = 5578

    lidar_port: str = ""
    lidar_auto_detect: bool = True
    lidar_baudrate: int = 230400
    lidar_topic: str = "/scan"

    history_db: str = "data/robot_history.db"

    control_password: str = os.getenv("GATEWAY_PASSWORD", "")


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()

settings = Settings(
    gateway_host=os.getenv("GATEWAY_HOST", "127.0.0.1"),
    gateway_port=_int("GATEWAY_PORT", 8000),
    allowed_origins=_csv("FRONTEND_ORIGINS",
                         "http://localhost:5173,http://127.0.0.1:5173,file://,null"),
    rosbridge_url=os.getenv("ROSBRIDGE_URL", "ws://127.0.0.1:9090"),
    usb_sensor_port=os.getenv("USB_SENSOR_PORT", ""),
    usb_sensor_auto_detect=os.getenv("USB_SENSOR_AUTO_DETECT", "true").lower() != "false",
    usb_sensor_baudrate=_int("USB_SENSOR_BAUDRATE", 9600),
    usb_sensor_slave_id=_int("USB_SENSOR_SLAVE_ID", 1),
    chassis_probe_enabled=os.getenv("CHASSIS_PROBE_ENABLED", "true").lower() != "false",
    chassis_host=os.getenv("CHASSIS_HOST", "192.168.0.7"),
    chassis_port=_int("CHASSIS_PORT", 5578),
    lidar_port=os.getenv("LIDAR_PORT", ""),
    lidar_auto_detect=os.getenv("LIDAR_AUTO_DETECT", "true").lower() != "false",
    lidar_baudrate=_int("LIDAR_BAUDRATE", 230400),
    history_db=os.getenv("HISTORY_DB", "data/robot_history.db"),
)
