#!/usr/bin/env python3
"""落地旋转标定：原地满速旋转数秒，人工数实际圈数，
算地面真实最大角速度，给出新的 MAX_ANGULAR_SPEED 推荐值。

背景：悬空标定的 MAX_ANGULAR_SPEED=16.0 在地面上会导致角速度命令
被压缩到 3~6%，地面摩擦下轮子几乎转不动。本脚本发满速(100%)旋转
测地面实际角速度，并推荐一个让日常 0.5 rad/s 命令落在 15% 左右的
新值（参考直线 0.2/1.257≈16% 能走的经验）。
"""
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

MAX_ANGULAR_SPEED = 16.0   # 当前 chassis_node.py 里的值（悬空标定）
DURATION = 4.0             # 满速旋转时长 s
RECOMMEND_CMD = 0.5        # 日常常用转向命令 rad/s
RECOMMEND_PCT = 0.15       # 期望该命令占满速百分比（参考直线约16%可走）


class RotCalibrate(Node):
    def __init__(self):
        super().__init__("rot_recalibrate")
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)

    def publish_cmd(self, angular=0.0):
        cmd = Twist()
        cmd.angular.z = float(angular)
        self.cmd_pub.publish(cmd)

    def stop(self):
        for _ in range(8):
            self.publish_cmd(0.0)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.05)


def main():
    rclpy.init()
    node = RotCalibrate()
    print("== 落地旋转标定 ==", flush=True)
    print(">>> 车放地面，周围 1 米内无障碍", flush=True)
    print(">>> 在车头上做个标记（如贴纸朝外），方便数圈", flush=True)
    print(">>> 车将原地满速旋转 %.0f 秒，随时 Ctrl+C 可停" % DURATION, flush=True)
    input(">>> 按回车开始: ")

    cmd_z = MAX_ANGULAR_SPEED  # 发当前满速值，chassis_node clamp 后=100%
    try:
        t0 = time.time()
        while time.time() - t0 < DURATION:
            node.publish_cmd(cmd_z)
            time.sleep(0.02)
    finally:
        node.stop()

    turns = float(input(">>> 数到的实际圈数（可带小数，如 4.5）: "))
    omega = turns * math.tau / DURATION
    rec = RECOMMEND_CMD / RECOMMEND_PCT
    predicted = RECOMMEND_PCT * omega

    print("", flush=True)
    print("========== 旋转标定结果 ==========", flush=True)
    print("满速实际角速度 = %.2f rad/s（%d 秒转 %.1f 圈）" % (omega, DURATION, turns), flush=True)
    print("", flush=True)
    print("推荐 MAX_ANGULAR_SPEED = %.2f" % rec, flush=True)
    print("  此时 0.5 rad/s 命令 -> %.0f%% -> 实际约 %.2f rad/s（转一圈约 %.1f 秒）"
          % (RECOMMEND_PCT * 100, predicted, math.tau / predicted), flush=True)
    print("  若实际偏慢转不动 -> 再调小该值；若太猛 -> 调大", flush=True)
    print("==================================", flush=True)
    print("修改位置: ~/lidar_patrol_ws/src/vehicle_bringup/vehicle_bringup/chassis_node.py 第18行", flush=True)
    print("改完重编译: colcon build --packages-select vehicle_bringup", flush=True)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
