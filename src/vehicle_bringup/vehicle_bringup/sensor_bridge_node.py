#!/usr/bin/env python3
"""sensor_bridge_node: 从 EnzoPatrolLab 实验台网关的 WebSocket 拉取传感器快照,
发布为 ROS2 标准话题 /sensor/temperature、/sensor/humidity、/sensor/noise (Float32)。

背景: 温湿度传感器(LES11B-MC-S1, Modbus RTU)由 Windows 端实验台软件直读,
串口被其占用, 本节点不复读串口, 而是消费它推送的 robot_status 快照,
使 ROS2 体系(Nav2/报警联动)能拿到环境数据。
"""
import asyncio
import json
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import websockets

TOPIC_MAP = {
    "temperature": "/sensor/temperature",
    "humidity": "/sensor/humidity",
    "noise": "/sensor/noise",
}


class SensorBridgeNode(Node):
    def __init__(self):
        super().__init__("sensor_bridge_node")
        self.declare_parameter("ws_url", "ws://127.0.0.1:8000/ws/robot")
        self.ws_url = self.get_parameter("ws_url").value
        self.pubs = {k: self.create_publisher(Float32, t, 10) for k, t in TOPIC_MAP.items()}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.get_logger().info(f"sensor_bridge 启动: {self.ws_url} -> {list(TOPIC_MAP.values())}")

    def _run_loop(self):
        asyncio.run(self._async_loop())

    async def _async_loop(self):
        delay = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                    delay = 1.0
                    self.get_logger().info("已连接实验台网关")
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        self._handle(raw)
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.get_logger().warn(f"连接断开: {e}", throttle_duration_sec=10.0)
            if not self._stop.is_set():
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15.0)

    def _handle(self, raw):
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if msg.get("type") != "robot_status":
            return
        sensors = msg.get("sensors") or {}
        for key, pub in self.pubs.items():
            value = sensors.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out = Float32()
                out.data = float(value)
                pub.publish(out)

    def destroy_node(self):
        self._stop.set()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = SensorBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
