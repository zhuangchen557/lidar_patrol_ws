#!/usr/bin/env python3
"""落地旋转标定：原地旋转数秒，人工数实际圈数，
算地面真实最大角速度，给出新的 MAX_ANGULAR_SPEED 推荐值。

背景：悬空标定的 MAX_ANGULAR_SPEED=16.0 在地面上会导致角速度命令
被压缩到 3~6%，地面摩擦下轮子几乎转不动。本脚本发固定比例旋转
测地面实际角速度，并推荐一个让日常 0.5 rad/s 命令落在 15% 左右的
新值（参考直线 0.2/1.257≈16% 能走的经验）。

用法：
  python3 scripts/recalibrate_rot.py                 # 满速 16.0 rad/s，转 4 秒
  python3 scripts/recalibrate_rot.py --speed 2.0     # 慢速 2.0 rad/s（车上有物品时）
  python3 scripts/recalibrate_rot.py --duration 6    # 自定义时长
"""
import argparse
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

MAX_ANGULAR_SPEED = 16.0   # 当前 chassis_node.py 里的值（悬空标定）
DURATION = 4.0             # 默认旋转时长 s
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
    parser = argparse.ArgumentParser(description="落地旋转标定")
    parser.add_argument("--speed", type=float, default=MAX_ANGULAR_SPEED,
                        help=f"命令角速度 rad/s（默认满速 {MAX_ANGULAR_SPEED}，车上有物品建议 1.0~2.0）")
    parser.add_argument("--duration", type=float, default=DURATION,
                        help=f"旋转时长 s（默认 {DURATION}）")
    args = parser.parse_args()

    cmd_z = max(0.1, min(MAX_ANGULAR_SPEED, args.speed))
    duration = max(1.0, args.duration)
    pct = cmd_z / MAX_ANGULAR_SPEED * 100

    rclpy.init()
    node = RotCalibrate()
    print("== 落地旋转标定 ==", flush=True)
    print(">>> 车放地面，周围 1 米内无障碍", flush=True)
    print(">>> 在车头上做个标记（如贴纸朝外），方便数圈", flush=True)
    print(">>> 车将原地以 %.2f rad/s（满速的 %.0f%%）旋转 %.0f 秒，随时 Ctrl+C 可停"
          % (cmd_z, pct, duration), flush=True)
    input(">>> 按回车开始: ")

    try:
        t0 = time.time()
        while time.time() - t0 < duration:
            node.publish_cmd(cmd_z)
            time.sleep(0.02)
    finally:
        node.stop()

    turns = float(input(">>> 数到的实际圈数（可带小数，如 2.5）: "))
    omega_measured = turns * math.tau / duration
    omega_full = omega_measured / pct * 100  # 反推满速实际角速度
    rec = RECOMMEND_CMD / RECOMMEND_PCT
    predicted = RECOMMEND_PCT * omega_full

    print("", flush=True)
    print("========== 旋转标定结果 ==========", flush=True)
    print("命令 %.2f rad/s（%.0f%% 出力）实际 = %.2f rad/s（%d 秒转 %.1f 圈）"
          % (cmd_z, pct, omega_measured, duration, turns), flush=True)
    print("反推满速实际角速度 = %.2f rad/s" % omega_full, flush=True)
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
