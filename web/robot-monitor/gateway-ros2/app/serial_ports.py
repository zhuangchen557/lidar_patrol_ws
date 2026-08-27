"""COM 口枚举与辅助函数（自动检测温湿度传感器用）。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

SERIAL_DISCOVERY_LOCK = threading.Lock()


@dataclass
class SerialPortInfo:
    device: str
    description: str


def serial_port_inventory() -> list[SerialPortInfo]:
    try:
        from serial.tools import list_ports
        return [
            SerialPortInfo(device=p.device, description=p.description or "")
            for p in list_ports.comports()
        ]
    except Exception:
        return []


def inventory_summary(inventory: Iterable[SerialPortInfo]) -> str:
    names = [info.device for info in inventory]
    return "、".join(names) if names else "无可用串口"


def is_auto_port(port: str) -> bool:
    return not port or port.lower() in ("auto", "com")


def ordered_port_names(configured: str, inventory: Iterable[SerialPortInfo]) -> list[str]:
    """auto 模式下按 CH340/CH341 优先排序的候选 COM 口列表。"""
    names = [info.device for info in inventory if info.device]
    if configured and configured.lower() not in ("auto", ""):
        return [configured]
    ch340 = [n for n in names if "CH340" in n.upper() or "CH341" in n.upper()]
    others = [n for n in names if n not in ch340]
    return ch340 + others
