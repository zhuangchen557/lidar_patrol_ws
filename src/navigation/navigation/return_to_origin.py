#!/usr/bin/env python3
"""
Return the patrol vehicle to the recorded route origin.

The route is recorded in the map frame. To return to the origin, this
node replays the recorded waypoints in reverse order and sends each
point to Nav2's /navigate_to_pose Action. The first recorded point is
therefore the final target.

This is intentionally separate from waypoint_player.py so normal
forward patrol behavior is unchanged.
"""

import json
import math
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose


class ReturnToOrigin(Node):
    def __init__(self, route_file):
        super().__init__("return_to_origin")

        self.declare_parameter("dwell_seconds", 1.0)
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("skip_current_point", True)
        self.dwell_seconds = float(self.get_parameter("dwell_seconds").value)
        self.map_frame = str(self.get_parameter("map_frame").value)
        self.skip_current_point = bool(
            self.get_parameter("skip_current_point").value
        )

        with open(route_file, "r", encoding="utf-8") as f:
            self.route = json.load(f)

        route_frame = self.route.get("frame_id", self.map_frame)
        if route_frame != self.map_frame:
            raise ValueError(
                f"路线 frame_id={route_frame}，但当前 map_frame={self.map_frame}"
            )

        self.points = self.route.get("points", [])
        if not self.points:
            raise ValueError("路线没有 waypoint，无法返回原点")

        self.client = ActionClient(self, NavigateToPose, "/navigate_to_pose")

    @staticmethod
    def yaw_to_quaternion(yaw):
        return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)

    def send_goal(self, point):
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
            self.get_logger().error(f"返回目标 {point['label']} 被 Nav2 拒绝")
            return False

        self.get_logger().info(
            f"返回 -> {point['label']} "
            f"x={point['x']:.3f}, y={point['y']:.3f}, yaw={point['yaw']:.3f}"
        )

        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        wrapped = result_future.result()
        if wrapped is None:
            self.get_logger().error("未收到 Nav2 返回结果")
            return False

        if wrapped.status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info(f"已到达 {point['label']}")
            return True

        self.get_logger().error(
            f"到达 {point['label']} 失败，status={wrapped.status}"
        )
        return False

    def run(self):
        # Reverse the route: last recorded point -> ... -> first point.
        reverse_points = list(reversed(self.points))

        # If the robot is currently exactly at the last recorded point,
        # avoid sending it to that same goal again. For robustness this
        # remains configurable; default True matches the normal use case.
        if self.skip_current_point and len(reverse_points) > 1:
            reverse_points = reverse_points[1:]

        origin = self.points[0]
        self.get_logger().info(
            f"开始返回原点：{origin['label']} "
            f"(x={origin['x']:.3f}, y={origin['y']:.3f})"
        )

        for point in reverse_points:
            if not self.send_goal(point):
                self.get_logger().error("返回路线中断，不再执行后续点")
                return False
            if self.dwell_seconds > 0:
                time.sleep(self.dwell_seconds)

        # If there was only one waypoint, or skip_current_point removed
        # everything, explicitly navigate to the first point.
        if not reverse_points or reverse_points[-1]["id"] != origin["id"]:
            if not self.send_goal(origin):
                self.get_logger().error("最终原点目标执行失败")
                return False

        self.get_logger().info("已返回录制路线原点")
        return True


def main(args=None):
    if len(sys.argv) < 2:
        print(
            "用法: ros2 run navigation return_to_origin "
            "routes/real_route.json"
        )
        return

    rclpy.init(args=args)
    node = ReturnToOrigin(sys.argv[1])
    try:
        ok = node.run()
    except KeyboardInterrupt:
        node.get_logger().info("用户中断返回")
        ok = False
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
