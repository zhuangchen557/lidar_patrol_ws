#!/usr/bin/env python3
"""
Waypoint recorder for the patrol vehicle.

Records the robot pose in the MAP frame by default; set
map_frame:=odom to record raw odometry poses (works without SLAM,
e.g. bench / wheel-off-ground validation).
"""

import json
import math
import os
from typing import Optional

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from tf2_ros import Buffer, TransformListener, TransformException


class WaypointRecorder(Node):
    def __init__(self):
        super().__init__("waypoint_recorder")

        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("output_file", "routes/route.json")
        self.declare_parameter("sample_interval", 2.0)
        self.declare_parameter("min_distance", 0.30)
        self.declare_parameter("min_yaw_change", 0.20)

        self.odom_topic = str(self.get_parameter("odom_topic").value)
        self.map_frame = str(self.get_parameter("map_frame").value)
        self.base_frame = str(self.get_parameter("base_frame").value)
        self.output_file = str(self.get_parameter("output_file").value)
        self.sample_interval = float(self.get_parameter("sample_interval").value)
        self.min_distance = float(self.get_parameter("min_distance").value)
        self.min_yaw_change = float(self.get_parameter("min_yaw_change").value)

        self.latest_odom: Optional[Odometry] = None
        self.last_sample_time = self.get_clock().now()
        self.last_x = None
        self.last_y = None
        self.last_yaw = None
        self.points = []

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.subscription = self.create_subscription(
            Odometry, self.odom_topic, self.odom_callback, 20
        )
        self.timer = self.create_timer(0.1, self.sample_pose)

        self.get_logger().info("Waypoint 录制器启动")
        if self.map_frame == "odom":
            self.get_logger().info("odom 模式：直接记录里程计位姿（无需 map TF）")
        else:
            self.get_logger().info(
                f"要求 TF: {self.map_frame} -> {self.base_frame}"
            )

    def odom_callback(self, msg: Odometry):
        self.latest_odom = msg

    @staticmethod
    def quat_to_yaw(q):
        return math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    @staticmethod
    def angle_diff(a, b):
        return math.atan2(math.sin(a - b), math.cos(a - b))

    def sample_pose(self):
        if self.latest_odom is None:
            return

        now = self.get_clock().now()
        elapsed = (now - self.last_sample_time).nanoseconds / 1e9
        if elapsed < self.sample_interval:
            return

        if self.map_frame == "odom":
            pose = self.latest_odom.pose.pose
            x = pose.position.x
            y = pose.position.y
            yaw = self.quat_to_yaw(pose.orientation)
        else:
            try:
                transform = self.tf_buffer.lookup_transform(
                    self.map_frame,
                    self.base_frame,
                    rclpy.time.Time(),
                    timeout=rclpy.duration.Duration(seconds=0.2),
                )
            except TransformException as exc:
                self.get_logger().warn(
                    f"暂时无法获取 {self.map_frame}->{self.base_frame} TF: {exc}",
                    throttle_duration_sec=3.0,
                )
                return
            x = transform.transform.translation.x
            y = transform.transform.translation.y
            yaw = self.quat_to_yaw(transform.transform.rotation)

        if self.last_x is not None:
            distance = math.hypot(x - self.last_x, y - self.last_y)
            yaw_change = abs(self.angle_diff(yaw, self.last_yaw))
            if distance < self.min_distance and yaw_change < self.min_yaw_change:
                return

        point_id = len(self.points) + 1
        self.points.append({
            "id": point_id,
            "x": round(x, 4),
            "y": round(y, 4),
            "yaw": round(yaw, 4),
            "label": f"巡检点{point_id}",
        })

        self.last_x = x
        self.last_y = y
        self.last_yaw = yaw
        self.last_sample_time = now

        self.get_logger().info(
            f"记录巡检点 {point_id}: "
            f"x={x:.3f}, y={y:.3f}, yaw={yaw:.3f}"
        )

    def save_route(self):
        route = {
            "route_name": "patrol_route",
            "frame_id": self.map_frame,
            "points": self.points,
        }
        directory = os.path.dirname(self.output_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(route, f, ensure_ascii=False, indent=4)
        self.get_logger().info(
            f"路线已保存: {self.output_file}，共 {len(self.points)} 个点"
        )


def main(args=None):
    rclpy.init(args=args)
    node = WaypointRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("停止录制")
    finally:
        node.save_route()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()