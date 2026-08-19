from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .database import init_database, insert_status, get_latest_status

app = FastAPI(title="巡检车后端服务", version="1.0.0")


class RobotStatus(BaseModel):
    x: float
    y: float
    yaw: float
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    noise: Optional[float] = None
    gas: Optional[float] = None


@app.on_event("startup")
def startup():
    init_database()


@app.get("/")
def root():
    return {"message": "巡检车 FastAPI 后端运行正常"}


@app.get("/robot/status")
def robot_status():
    return get_latest_status() or {"message": "暂无机器人数据"}


@app.post("/robot/status")
def receive_robot_status(status: RobotStatus):
    timestamp = datetime.now(timezone.utc).isoformat()
    insert_status(
        timestamp, status.x, status.y, status.yaw,
        status.temperature, status.humidity, status.noise, status.gas
    )
    return {"success": True, "timestamp": timestamp}
