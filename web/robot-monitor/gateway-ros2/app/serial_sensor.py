"""LES11B 温湿度传感器（Modbus RTU 9600 8N1 slave 1）串口读取。

协议：读保持寄存器 0x0000 数量 2（温度、湿度），温度/湿度 = raw / 10。
核心 CRC 与解码逻辑来自 0.2.0 robot_gateway.exe 反编译（serial_sensor.pyc）。
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import suppress
from typing import Awaitable, Callable

from .config import settings
from .serial_ports import SERIAL_DISCOVERY_LOCK, inventory_summary, is_auto_port, ordered_port_names, serial_port_inventory

StatusCallback = Callable[[bool, str], Awaitable[None]]
ReadingCallback = Callable[[float, float], Awaitable[None]]

READ_INTERVAL = 1.0


def modbus_crc16(payload: bytes) -> int:
    crc = 0xFFFF
    for value in payload:
        crc ^= value
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_read_request(slave_id: int, start_register: int = 0, quantity: int = 2) -> bytes:
    payload = bytes((slave_id, 0x03, start_register >> 8 & 0xFF, start_register & 0xFF,
                     quantity >> 8 & 0xFF, quantity & 0xFF))
    crc = modbus_crc16(payload)
    return payload + bytes((crc & 0xFF, crc >> 8 & 0xFF))


def decode_temp_humidity_response(frame: bytes, slave_id: int) -> tuple[float, float]:
    if len(frame) == 5 and frame[0] == slave_id and frame[1] & 0x80:
        raise ValueError(f"Modbus device returned exception code {frame[2]}")
    if len(frame) != 9:
        raise ValueError(f"Expected 9 response bytes, received {len(frame)}")
    if frame[0] != slave_id or frame[1] != 0x03 or frame[2] != 0x04:
        raise ValueError("Unexpected Modbus response header")
    expected_crc = modbus_crc16(frame[:-2])
    received_crc = frame[-2] | frame[-1] << 8
    if received_crc != expected_crc:
        raise ValueError("Modbus CRC check failed")
    temperature_raw = frame[3] << 8 | frame[4]
    if temperature_raw & 0x8000:
        temperature_raw -= 0x10000
    humidity_raw = frame[5] << 8 | frame[6]
    temperature = temperature_raw / 10
    humidity = humidity_raw / 10
    if not -40 <= temperature <= 125:
        raise ValueError("Sensor reading is outside the SHT40 operating range")
    if not 0 <= humidity <= 100:
        raise ValueError("Sensor reading is outside the SHT40 operating range")
    return temperature, humidity


class SerialTemperatureHumidityReader:
    def __init__(self, on_status: StatusCallback, on_reading: ReadingCallback) -> None:
        self.on_status = on_status
        self.on_reading = on_reading
        self._serial = None
        self._stopping = False
        self._connected = False
        self.active_port = None
        self.last_inventory: list = []

    @property
    def enabled(self) -> bool:
        if settings.usb_sensor_auto_detect:
            return True
        return bool(settings.usb_sensor_port) and not is_auto_port(settings.usb_sensor_port)

    async def run(self) -> None:
        if not self.enabled:
            await self.on_status(False, "温湿度检测已禁用")
            return
        while not self._stopping:
            if self._serial is None:
                with SERIAL_DISCOVERY_LOCK:
                    self._open()
            if self._serial is not None:
                try:
                    reading = await asyncio.to_thread(self._read_frame)
                    if reading is not None:
                        await self.on_reading(*reading)
                except Exception as exc:
                    self._close()
                    await self.on_status(False, f"温湿度读取失败：{exc}")
            await asyncio.sleep(READ_INTERVAL)

    async def stop(self) -> None:
        self._stopping = True
        await asyncio.sleep(0.2)
        self._close()

    async def _set_status(self, connected: bool, detail: str) -> None:
        if connected != self._connected:
            self._connected = connected
        await self.on_status(connected, detail)

    def _open(self) -> None:
        import serial
        self.last_inventory = serial_port_inventory()
        if settings.usb_sensor_auto_detect:
            candidates = ordered_port_names(settings.usb_sensor_port, self.last_inventory)
        elif settings.usb_sensor_port and not is_auto_port(settings.usb_sensor_port):
            candidates = [settings.usb_sensor_port]
        else:
            candidates = []
        if not candidates:
            raise RuntimeError("Windows 未发现串口设备；请检查 USB 连接或串口驱动")

        errors: list[str] = []
        for port_name in candidates:
            serial_port = None
            try:
                serial_port = serial.Serial(
                    port=port_name,
                    baudrate=settings.usb_sensor_baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.8,
                    write_timeout=0.8,
                )
                request = build_read_request(settings.usb_sensor_slave_id)
                serial_port.reset_input_buffer()
                serial_port.write(request)
                serial_port.flush()
                response = serial_port.read(9)
                reading = decode_temp_humidity_response(response, settings.usb_sensor_slave_id)
                self._serial = serial_port
                self.active_port = port_name
                asyncio.create_task(self._set_status(True, f"{port_name} 已识别为温湿度传感器"))
                return
            except Exception as exc:
                if serial_port is not None:
                    with suppress(Exception):
                        serial_port.close()
                errors.append(f"{port_name}: {exc}")
        summary = inventory_summary(self.last_inventory)
        raise RuntimeError(f"未识别到 LES11B 温湿度传感器；已扫描 {summary}")

    def _read_frame(self):
        if self._serial is None:
            return None
        self._serial.reset_input_buffer()
        self._serial.write(build_read_request(settings.usb_sensor_slave_id))
        self._serial.flush()
        frame = self._serial.read(9)
        return decode_temp_humidity_response(frame, settings.usb_sensor_slave_id)

    def _close(self) -> None:
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            with suppress(Exception):
                serial_port.close()
