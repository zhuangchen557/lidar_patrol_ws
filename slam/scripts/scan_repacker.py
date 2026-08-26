#!/usr/bin/env python3
"""把 LD06 变长 /scan 重采样成固定点数 /scan_fixed.

usbipd 传输抖动会造成整圈拼包错乱(点数 84~542 乱跳), 而 slam_toolbox 以
第一帧点数为基准, 点数不匹配的帧一律拒收(日志刷 LaserRangeScan contains
X range readings, expected Y). 本节点按角度最近邻重采样到固定点数, 坏帧
(点数过少)直接丢弃, 给 slam_toolbox / rf2o 提供一致的数据流.
"""
import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class ScanRepacker(Node):

    def __init__(self) -> None:
        super().__init__('scan_repacker')
        self.declare_parameter('input_topic', '/scan')
        self.declare_parameter('output_topic', '/scan_fixed')
        self.declare_parameter('output_count', 360)
        self.declare_parameter('min_input_points', 300)
        self.n_out = int(self.get_parameter('output_count').value)
        self.min_in = int(self.get_parameter('min_input_points').value)
        self.sub = self.create_subscription(
            LaserScan, self.get_parameter('input_topic').value, self.cb, 10)
        self.pub = self.create_publisher(
            LaserScan, self.get_parameter('output_topic').value, 10)
        self.dropped = 0
        self.sent = 0
        self.get_logger().info(
            f'repacker: {self.get_parameter("input_topic").value} -> '
            f'{self.get_parameter("output_topic").value}, '
            f'{self.n_out}点/帧, <{self.min_in}点判坏帧')

    def cb(self, msg: LaserScan) -> None:
        n = len(msg.ranges)
        if n < self.min_in:
            self.dropped += 1
            if self.dropped % 50 == 1:
                self.get_logger().warn(f'坏帧丢弃 #{self.dropped}: 仅 {n} 点')
            return
        angles = [msg.angle_min + i * msg.angle_increment for i in range(n)]
        out_angle_inc = 2.0 * math.pi / self.n_out
        ranges = []
        j = 0
        for i in range(self.n_out):
            a = msg.angle_min + i * out_angle_inc
            while j < n - 1 and abs(angles[j + 1] - a) <= abs(angles[j] - a):
                j += 1
            ranges.append(float(msg.ranges[j]))
        out = LaserScan()
        out.header = msg.header
        out.angle_min = msg.angle_min
        out.angle_max = msg.angle_min + out_angle_inc * (self.n_out - 1)
        out.angle_increment = out_angle_inc
        out.time_increment = msg.time_increment
        out.scan_time = msg.scan_time
        out.range_min = msg.range_min
        out.range_max = msg.range_max
        out.ranges = ranges
        self.pub.publish(out)
        self.sent += 1
        if self.sent % 100 == 0:
            self.get_logger().info(f'已发布 {self.sent} 帧, 累计丢弃 {self.dropped} 坏帧')


def main() -> None:
    rclpy.init()
    node = ScanRepacker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
