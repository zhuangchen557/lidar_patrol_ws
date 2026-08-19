#!/usr/bin/env python3
"""
Waypoint player.

Reads route JSON in the map frame and sends each point to Nav2
through /navigate_to_pose. After a successful arrival, the robot
stays for a configurable number of seconds before the next point.
"""

import json
import math
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from nav2_msgs.action import NavigateToPose
from action_msgs.msg import GoalStatus


class WaypointPlayer(Node):
    def __init__(self, route_file):
        super().__init__("waypoint_player")

        self.declare_parameter("dwell_seconds", 3.0)
        self.declare_parameter("map_frame", "map")
        self.dwell_seconds = float(self.get_parameter("dwell_seconds").value)
        self.map_frame = str(self.get_parameter("map_frame").value)

        self.client = ActionClient(self, NavigateToPose, "/navigate_to_pose")

        with open(route_file, "r", encoding="utf-8") as f:
            self.route = json.load(f)

        route_frame = self.route.get("frame_id", self.map_frame)
        if route_frame != self.map_frame:
            raise ValueError(
                f"路线 frame_id={route_frame}，但当前 map_frame={self.map_frame}"
            )

    @staticmethod
    def yaw_to_quaternion(yaw):
        return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)

    def send_goal(self, point):
        self.get_logger().info(
            f"等待 Nav2 /navigate_to_pose: {point['label']}"
        )
        if not self.client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("未发现 /navigate_to_pose Action Server")
            return False

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = self.map_frame
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(point["x"])
        goal.pose.pose.position.y = float(point["y"])

        qx, qy, qz, qw = self.yaw_to_quaternion(float(point["yaw"]))
        goal.pose.pose.orientation.x = qx
        goal.pose.pose.orientation.y = qy
        goal.pose.pose.orientation.z = qz
        goal.pose.pose.orientation.w = qw

        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        handle = future.result()

        if handle is None or not handle.accepted:
            self.get_logger().error(f"{point['label']} 被 Nav2 拒绝")
            return False

        self.get_logger().info(
            f"已发送 {point['label']}: "
            f"x={point['x']}, y={point['y']}, yaw={point['yaw']}"
        )

        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        wrapped_result = result_future.result()

        if wrapped_result is None:
            self.get_logger().error("未收到 Nav2 结果")
            return False

        success = wrapped_result.status == GoalStatus.STATUS_SUCCEEDED
        if success:
            self.get_logger().info(f"{point['label']} 到达成功")
        else:
            self.get_logger().error(
                f"{point['label']} 导航失败，status={wrapped_result.status}"
            )
        return success

    def run(self):
        points = self.route.get("points", [])
        if not points:
            self.get_logger().error("路线为空")
            return

        self.get_logger().info(
            f"开始巡检：{self.route.get('route_name', 'unnamed')}，"
            f"共 {len(points)} 个点"
        )

        for point in points:
            if not self.send_goal(point):
                self.get_logger().error("停止后续巡检点")
                return
            self.get_logger().info(
                f"{point['label']} 停留 {self.dwell_seconds:.1f} 秒"
            )
            time.sleep(self.dwell_seconds)

        self.get_logger().info("整条巡检路线执行完成")


def main(args=None):
    if len(sys.argv) < 2:
        print(
            "用法: ros2 run navigation waypoint_player "
            "routes/route.json"
        )
        return

    rclpy.init(args=args)
    node = WaypointPlayer(sys.argv[1])
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
