#!/usr/bin/env python3
"""
Waypoint player.

Default: sends each route point to Nav2 through /navigate_to_pose.

Bench mode (use_nav2:=false): drives directly with /cmd_vel using odom
feedback, no SLAM/Nav2 required. Use it to validate record/replay
logic on a wheel-off-ground vehicle.
"""

import json
import math
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

LINEAR_SPEED = 0.4       # m/s (direct mode)
YAW_TOL = 0.06           # rad
POS_TOL = 0.06           # m
MAX_ANGULAR = 1.0        # normalized command limit


def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


class WaypointPlayer(Node):
    def __init__(self, route_file):
        super().__init__("waypoint_player")

        self.declare_parameter("dwell_seconds", 3.0)
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("use_nav2", True)
        self.dwell_seconds = float(self.get_parameter("dwell_seconds").value)
        self.map_frame = str(self.get_parameter("map_frame").value)
        self.use_nav2 = bool(self.get_parameter("use_nav2").value)

        with open(route_file, "r", encoding="utf-8") as f:
            self.route = json.load(f)

        route_frame = self.route.get("frame_id", self.map_frame)
        if route_frame != self.map_frame:
            raise ValueError(
                f"路线 frame_id={route_frame}，但当前 map_frame={self.map_frame}"
            )

        if self.use_nav2:
            from nav2_msgs.action import NavigateToPose
            from action_msgs.msg import GoalStatus
            self.NavigateToPose = NavigateToPose
            self.GoalStatus = GoalStatus
            self.client = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        else:
            self.latest_odom = None
            self.odom_sub = self.create_subscription(
                Odometry, "/odom", self.odom_cb, 10
            )
            self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)
            self.get_logger().info(
                "直接回放模式（use_nav2=false）：odom 闭环 + /cmd_vel"
            )

    def odom_cb(self, msg: Odometry):
        self.latest_odom = msg

    @staticmethod
    def yaw_to_quaternion(yaw):
        return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)

    @staticmethod
    def quat_to_yaw(q):
        return math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    @staticmethod
    def angle_diff(a, b):
        return math.atan2(math.sin(a - b), math.cos(a - b))

    def publish_cmd(self, linear=0.0, angular=0.0):
        cmd = Twist()
        cmd.linear.x = float(linear)
        cmd.angular.z = float(angular)
        self.cmd_pub.publish(cmd)

    def stop(self):
        for _ in range(5):
            self.publish_cmd()
            time.sleep(0.05)

    def spin_wait(self, timeout_s=0.2):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.005)

    def get_pose(self):
        if self.latest_odom is None:
            return None
        p = self.latest_odom.pose.pose
        return p.position.x, p.position.y, self.quat_to_yaw(p.orientation)

    def wait_odom(self, timeout_s=5.0):
        t0 = time.time()
        while self.latest_odom is None and time.time() - t0 < timeout_s:
            self.spin_wait(0.1)
        return self.latest_odom is not None

    def rotate_to(self, target_yaw, timeout_s=10.0):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            pose = self.get_pose()
            if pose is None:
                self.spin_wait()
                continue
            err = self.angle_diff(target_yaw, pose[2])
            if abs(err) < YAW_TOL:
                break
            self.publish_cmd(angular=clamp(err * 2.0, -MAX_ANGULAR, MAX_ANGULAR))
            self.spin_wait(0.02)
        self.stop()

    def drive_to_xy(self, tx, ty, timeout_s=20.0):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            pose = self.get_pose()
            if pose is None:
                self.spin_wait()
                continue
            x, y, yaw = pose
            dx, dy = tx - x, ty - y
            dist = math.hypot(dx, dy)
            if dist < POS_TOL:
                break
            target_angle = math.atan2(dy, dx)
            ang_err = self.angle_diff(target_angle, yaw)
            self.publish_cmd(
                linear=LINEAR_SPEED,
                angular=clamp(ang_err * 1.5, -MAX_ANGULAR, MAX_ANGULAR),
            )
            self.spin_wait(0.02)
        self.stop()

    def drive_to_point(self, point):
        tx = float(point["x"])
        ty = float(point["y"])
        tyaw = float(point["yaw"])
        self.get_logger().info(
            f"直接回放 {point['label']}: x={tx:.3f}, y={ty:.3f}, yaw={tyaw:.3f}"
        )
        if not self.wait_odom():
            self.get_logger().error("超时未收到 /odom")
            return False
        self.rotate_to(tyaw, timeout_s=10.0)
        self.drive_to_xy(tx, ty, timeout_s=20.0)
        self.rotate_to(tyaw, timeout_s=5.0)
        self.get_logger().info(f"{point['label']} 到达")
        return True

    def send_goal(self, point):
        if not self.use_nav2:
            return self.drive_to_point(point)

        self.get_logger().info(
            f"等待 Nav2 /navigate_to_pose: {point['label']}"
        )
        if not self.client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("未发现 /navigate_to_pose Action Server")
            return False

        goal = self.NavigateToPose.Goal()
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

        success = wrapped_result.status == self.GoalStatus.STATUS_SUCCEEDED
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
            "routes/route.json --ros-args -p use_nav2:=false"
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