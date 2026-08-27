from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    rosbridge_url: str = os.getenv("ROSBRIDGE_URL", "ws://127.0.0.1:9090")
    control_password: str = os.getenv("ROBOT_CONTROL_PASSWORD", "")
    allowed_origins: tuple[str, ...] = _csv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )

    temperature_topic: str = os.getenv("ROS_TOPIC_TEMPERATURE", "/sensor/temperature")
    humidity_topic: str = os.getenv("ROS_TOPIC_HUMIDITY", "/sensor/humidity")
    temp_humidity_topic: str = os.getenv("ROS_TOPIC_TEMP_HUM", "/sensor/temp_hum")
    noise_topic: str = os.getenv("ROS_TOPIC_NOISE", "/sensor/noise")
    odom_topic: str = os.getenv("ROS_TOPIC_ODOM", "/odom")
    battery_topic: str = os.getenv("ROS_TOPIC_BATTERY", "/battery_state")
    mission_state_topic: str = os.getenv("ROS_TOPIC_MISSION_STATE", "/patrol/state")
    command_topic: str = os.getenv("ROS_TOPIC_COMMAND", "/patrol/command")

    history_db: Path = Path(
        os.getenv(
            "HISTORY_DB",
            str(Path(__file__).resolve().parents[1] / "data" / "robot_history.db"),
        )
    )
    stale_after_seconds: float = float(os.getenv("ROBOT_STALE_AFTER", "5"))
    broadcast_interval_seconds: float = float(os.getenv("BROADCAST_INTERVAL", "1"))


settings = Settings()
