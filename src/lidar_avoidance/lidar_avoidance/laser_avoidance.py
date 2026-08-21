#!/usr/bin/env python3
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist


class LaserAvoidance(Node):
    """
    Standalone obstacle-avoidance test node.

    /scan (sensor_msgs/LaserScan)
          -> sector distance analysis
          -> /cmd_vel (geometry_msgs/Twist)

    This is intended for bring-up/testing. The project's final navigation
    architecture should use Nav2 local_costmap + DWB as specified in the
    project plan.
    """

    def __init__(self):
        super().__init__('laser_avoidance')

        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('safe_distance', 1.0)
        self.declare_parameter('stop_distance', 0.50)
        self.declare_parameter('forward_speed', 0.20)
        self.declare_parameter('slow_speed', 0.10)
        self.declare_parameter('turn_speed', 0.55)
        self.declare_parameter('front_angle_deg', 25.0)
        self.declare_parameter('side_angle_deg', 70.0)

        scan_topic = self.get_parameter('scan_topic').value
        cmd_vel_topic = self.get_parameter('cmd_vel_topic').value

        self.safe_distance = float(self.get_parameter('safe_distance').value)
        self.stop_distance = float(self.get_parameter('stop_distance').value)
        self.forward_speed = float(self.get_parameter('forward_speed').value)
        self.slow_speed = float(self.get_parameter('slow_speed').value)
        self.turn_speed = float(self.get_parameter('turn_speed').value)
        self.front_angle = math.radians(
            float(self.get_parameter('front_angle_deg').value)
        )
        self.side_angle = math.radians(
            float(self.get_parameter('side_angle_deg').value)
        )

        self.cmd_pub = self.create_publisher(Twist, cmd_vel_topic, 10)
        self.scan_sub = self.create_subscription(
            LaserScan, scan_topic, self.scan_callback, 10
        )

        self.last_log = self.get_clock().now()
        self.get_logger().info(
            f'Laser avoidance started: {scan_topic} -> {cmd_vel_topic}, '
            f'safe={self.safe_distance:.2f}m, stop={self.stop_distance:.2f}m'
        )

    @staticmethod
    def valid_range(value, scan):
        return (
            math.isfinite(value)
            and value >= scan.range_min
            and value <= scan.range_max
        )

    def sector_min(self, scan, center, half_width):
        values = []
        angle = scan.angle_min

        for r in scan.ranges:
            if -math.pi <= angle <= math.pi:
                diff = math.atan2(math.sin(angle - center),
                                  math.cos(angle - center))
                if abs(diff) <= half_width and self.valid_range(r, scan):
                    values.append(r)
            angle += scan.angle_increment

        return min(values) if values else float('inf')

    def scan_callback(self, scan):
        front = self.sector_min(scan, 0.0, self.front_angle)
        left = self.sector_min(scan, math.pi / 2.0, self.side_angle)
        right = self.sector_min(scan, -math.pi / 2.0, self.side_angle)

        cmd = Twist()

        # No valid front reading: fail safe by stopping.
        if not math.isfinite(front):
            self.cmd_pub.publish(cmd)
            return

        if front < self.stop_distance:
            # Stop first, then turn toward the side with more free space.
            cmd.linear.x = 0.0
            cmd.angular.z = self.turn_speed if left > right else -self.turn_speed
            state = 'TURN'

        elif front < self.safe_distance:
            # Slow down when an obstacle is inside the safety distance.
            cmd.linear.x = self.slow_speed
            cmd.angular.z = 0.0
            state = 'SLOW'

        else:
            cmd.linear.x = self.forward_speed
            cmd.angular.z = 0.0
            state = 'FORWARD'

        self.cmd_pub.publish(cmd)

        now = self.get_clock().now()
        if (now - self.last_log).nanoseconds > 1_000_000_000:
            self.get_logger().info(
                f'{state}: front={front:.2f}m left={left:.2f}m right={right:.2f}m '
                f'cmd=({cmd.linear.x:.2f}, {cmd.angular.z:.2f})'
            )
            self.last_log = now


def main(args=None):
    rclpy.init(args=args)
    node = LaserAvoidance()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.cmd_pub.publish(Twist())
        except Exception:
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
