#!/usr/bin/env python3
"""分析 /scan：前方障碍物检测（±45°、±90°、360° 最近点）"""
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from sensor_msgs.msg import LaserScan


class ScanAnalyzer(Node):
    def __init__(self):
        super().__init__("scan_analyzer")
        qos = QoSProfile(depth=5, reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.VOLATILE)
        self.sub = self.create_subscription(LaserScan, "/scan", self.cb, qos)

    def cb(self, msg):
        n = len(msg.ranges)
        angle_min = msg.angle_min
        inc = msg.angle_increment

        def dist_at(angle_deg):
            a = math.radians(angle_deg)
            i = int(round((a - angle_min) / inc)) % n
            return msg.ranges[i]

        def nearest_in_sector(center_deg, half_width_deg):
            best = None
            for a in range(center_deg - half_width_deg, center_deg + half_width_deg + 1):
                d = dist_at(a)
                if d is None or math.isnan(d) or d <= 0.05 or d > 25:
                    continue
                if best is None or d < best[1]:
                    best = (a, d)
            return best

        fwd45 = nearest_in_sector(0, 45)
        fwd90 = nearest_in_sector(0, 90)
        left = nearest_in_sector(90, 30)
        right = nearest_in_sector(-90, 30)
        back = nearest_in_sector(180, 30)

        print("========== 障碍物分析 ==========")
        print(f"前方±45°:  {'无障碍' if fwd45 is None else f'最近 {fwd45[1]:.2f}m @ {fwd45[0]}°'}")
        print(f"前方±90°:  {'无障碍' if fwd90 is None else f'最近 {fwd90[1]:.2f}m @ {fwd90[0]}°'}")
        print(f"左方30°扇区: {'无障碍' if left is None else f'{left[1]:.2f}m @ {left[0]}°'}")
        print(f"右方30°扇区: {'无障碍' if right is None else f'{right[1]:.2f}m @ {right[0]}°'}")
        print(f"后方:       {'无障碍' if back is None else f'{back[1]:.2f}m @ {back[0]}°'}")
        print(f"点数: {n}")
        rclpy.shutdown()


def main():
    rclpy.init()
    node = ScanAnalyzer()
    rclpy.spin(node)


if __name__ == "__main__":
    main()
