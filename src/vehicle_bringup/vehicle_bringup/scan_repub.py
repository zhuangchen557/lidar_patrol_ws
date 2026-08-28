#!/usr/bin/env python3
"""/scan 双 QoS 转发：LD19 发布 BEST_EFFORT，rosbridge/gateway 默认 RELIABLE 订阅收不到。
本节点订阅 /scan(BEST_EFFORT) 并以 RELIABLE 重新发布到同一 /scan，使 Windows 侧
EnzoPatrolLab/Web 通过 rosbridge 能收到雷达数据。
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from sensor_msgs.msg import LaserScan


class ScanRepub(Node):
    def __init__(self):
        super().__init__("scan_repub")
        qos_best = QoSProfile(
            depth=5,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        qos_rel = QoSProfile(
            depth=5,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self.sub = self.create_subscription(LaserScan, "/scan", self.cb, qos_best)
        self.pub = self.create_publisher(LaserScan, "/scan", qos_rel)
        self.count = 0
        self.get_logger().info("scan_repub: /scan(BEST_EFFORT) -> /scan(RELIABLE)")

    def cb(self, msg):
        self.count += 1
        if self.count % 1000 == 0:
            self.get_logger().info(f"转发了 {self.count} 帧")
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = ScanRepub()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
