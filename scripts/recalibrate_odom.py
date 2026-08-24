#!/usr/bin/env python3
"""落地标定复核：车对墙直走，用 /scan 最近距离变化测实际位移，
对比 odom 理论位移，算出落地修正系数与新 MAX_LINEAR_SPEED"""
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan

MAX_LINEAR_SPEED = 1.257   # 当前悬空标定值
CMD_LINEAR = 0.6           # 测试速度 m/s
DURATION = 2.0             # 行驶时长 s
MIN_SCAN_RANGE = 0.35      # 雷达盲区

class Recalibrate(Node):
    def __init__(self):
        super().__init__("odom_recalibrate")
        self.scan = None
        self.odom = None
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.scan_sub = self.create_subscription(LaserScan, "/scan", self.scan_cb, 10)
        self.odom_sub = self.create_subscription(Odometry, "/odom", self.odom_cb, 10)

    def scan_cb(self, msg: LaserScan):
        self.scan = msg

    def odom_cb(self, msg: Odometry):
        self.odom = msg

    def nearest_range(self):
        if self.scan is None:
            return None
        valid = [r for r in self.scan.ranges
                 if r > MIN_SCAN_RANGE and math.isfinite(r)]
        return min(valid) if valid else None

    def publish_cmd(self, linear=0.0):
        cmd = Twist()
        cmd.linear.x = float(linear)
        self.cmd_pub.publish(cmd)

    def stop(self):
        for _ in range(8):
            self.publish_cmd(0.0)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.05)

    def spin_wait(self, timeout_s=0.3):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.005)

    def wait_data(self, timeout_s=10):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            self.spin_wait(0.2)
            if self.scan is not None and self.odom is not None:
                return True
        return False

    def run(self):
        print("== 落地标定复核（雷达测距法）==", flush=True)
        print(">>> 请把车放地上，车头对准 1.5~3 米外的墙/障碍物", flush=True)
        input(">>> 摆好后按回车确认（车会向前走 2 秒）")

        if not self.wait_data():
            print("错误：未收到 /scan 或 /odom，确认 bringup 在运行")
            return None

        d1 = self.nearest_range()
        x1 = self.odom.pose.pose.position.x
        print(f"起始：前方最近距离 {d1:.3f} m", flush=True)

        self.publish_cmd(CMD_LINEAR)
        time.sleep(DURATION)
        self.stop()
        self.spin_wait(0.5)

        d2 = self.nearest_range()
        x2 = self.odom.pose.pose.position.x
        print(f"结束：前方最近距离 {d2:.3f} m", flush=True)

        if d1 is None or d2 is None:
            print("错误：无法读取有效雷达距离")
            return None

        actual = d1 - d2
        odom_dx = x2 - x1
        print(f"实际位移（雷达）: {actual:.3f} m   odom 报告: {odom_dx:.3f} m", flush=True)
        if odom_dx <= 0:
            print("错误：odom 位移异常（车没动？）")
            return None

        factor = actual / odom_dx
        new_max = MAX_LINEAR_SPEED * factor
        print("", flush=True)
        print("========== 落地复核结果 ==========", flush=True)
        print(f"修正系数 factor        = {factor:.3f}", flush=True)
        print(f"新 MAX_LINEAR_SPEED    = {new_max:.3f}  (原 {MAX_LINEAR_SPEED})", flush=True)
        print("==================================", flush=True)
        print("建议跑 2~3 次取平均。angle 的落地复核暂不做（悬空误差主要在线速度）。", flush=True)
        return new_max


def main(args=None):
    rclpy.init(args=args)
    node = Recalibrate()
    try:
        node.run()
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()