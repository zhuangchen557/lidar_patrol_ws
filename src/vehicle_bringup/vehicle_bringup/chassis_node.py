#!/usr/bin/env python3
"""
底盘控制 ROS2 节点
接收 /cmd_vel 话题 → 调用 YK_CAN SDK 控制四轮差速小车
发布 /odom 里程计和 odom→base_link TF 变换
"""

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, Quaternion, TransformStamped
from nav_msgs.msg import Odometry
from tf2_ros import TransformBroadcaster


# ============ 待校准参数 ============
MAX_LINEAR_SPEED = 1.257     # 最大线速度 m/s（实测标定：5s空转6.25圈，周长1.005m）
MAX_ANGULAR_SPEED = 16.0     # 最大角速度 rad/s（实测标定：转1圈实际16圈）
WHEEL_BASE = 0.35            # 前后轴距 米（需要实测）


class ChassisNode(Node):
    def __init__(self):
        super().__init__("chassis_node")

        # --- 尝试导入 YK_CAN SDK ---
        self.car = None
        try:
            import sys
            sys.path.insert(0, "/home/sagac1ty/can_sdk")
            from yk_can_sdk import FourWheelVehicle, VehicleConfig
            from yk_can_sdk.config import NetworkConfig

            can_host = self.declare_parameter("can_host", "127.0.0.1").value
            can_port = self.declare_parameter("can_port", 5578).value
            config = VehicleConfig(network=NetworkConfig(host=can_host, port=can_port))
            self.car = FourWheelVehicle(config)
            self.car.connect()
            self.get_logger().info(f"YK_CAN SDK 已加载，已连接 CAN115 ({can_host}:{can_port})")
            # --- 自动重连：CAN115 连接断开后每 2s 尝试恢复 ---
            self.create_timer(2.0, self._check_connection)
        except Exception as e:
            self.get_logger().warn(f"YK_CAN SDK 不可用: {e}，将以模拟模式运行")

        # --- 订阅 /cmd_vel ---
        self.cmd_sub = self.create_subscription(
            Twist, "/cmd_vel", self.cmd_callback, 10
        )

        # --- 发布 /odom ---
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)

        # --- TF 广播 ---
        self.tf_broadcaster = TransformBroadcaster(self)

        # --- 里程计状态 ---
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.last_time = self.get_clock().now()
        self.last_cmd_linear = 0.0
        self.last_cmd_angular = 0.0

        # --- 定时发布 /odom（50Hz） ---
        self.odom_timer = self.create_timer(0.02, self.publish_odom)

        # --- 看门狗：如果 0.5s 没收到 /cmd_vel，自动停车 ---
        self.watchdog_timer = self.create_timer(0.1, self.watchdog_check)
        self.last_cmd_time = self.get_clock().now()

        self.get_logger().info("底盘节点启动完成")

    def _check_connection(self):
        """连接断开后自动重连（SDK 自身不重连，断了会永久报错）"""
        if self.car is None or self.car.is_connected:
            return
        self.get_logger().warn("底盘连接断开，尝试重连...")
        try:
            self.car.close()
            self.car.connect()
            self.get_logger().info("底盘已自动重连")
        except Exception as e:
            self.get_logger().warn(f"底盘重连失败: {e}")

    def cmd_callback(self, msg: Twist):
        """接收 /cmd_vel 指令 → 归一化到 [-1,1] → 调用 set_motion"""
        self.last_cmd_time = self.get_clock().now()

        lin_norm = max(-1.0, min(1.0, msg.linear.x / MAX_LINEAR_SPEED))
        ang_norm = max(-1.0, min(1.0, msg.angular.z / MAX_ANGULAR_SPEED))
        self.last_cmd_linear = lin_norm * MAX_LINEAR_SPEED
        self.last_cmd_angular = ang_norm * MAX_ANGULAR_SPEED

        if self.car is not None:
            try:
                self.car.set_motion(linear=lin_norm, angular=ang_norm)
            except Exception as e:
                self.get_logger().error(f"set_motion 失败: {e}")

    def watchdog_check(self):
        """看门狗：如果超时未收到 /cmd_vel，停车"""
        now = self.get_clock().now()
        dt = (now - self.last_cmd_time).nanoseconds / 1e9
        if dt > 0.5:
            if self.car is not None:
                try:
                    self.car.set_motion(linear=0.0, angular=0.0)
                except Exception:
                    pass
            self.last_cmd_linear = 0.0
            self.last_cmd_angular = 0.0

    def publish_odom(self):
        """发布里程计 + TF"""
        now = self.get_clock().now()
        dt = (now - self.last_time).nanoseconds / 1e9
        self.last_time = now

        if dt <= 0:
            return

        # --- 根据最近一次 /cmd_vel 推算位姿（last_cmd_* 已是物理值） ---
        vx = self.last_cmd_linear
        vth = self.last_cmd_angular

        delta_x = vx * math.cos(self.theta) * dt
        delta_y = vx * math.sin(self.theta) * dt
        delta_theta = vth * dt

        self.x += delta_x
        self.y += delta_y
        self.theta += delta_theta

        # --- 构建 Odometry 消息 ---
        odom = Odometry()
        odom.header.stamp = now.to_msg()
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation = _yaw_to_quat(self.theta)

        odom.twist.twist.linear.x = vx
        odom.twist.twist.angular.z = vth

        self.odom_pub.publish(odom)

        # --- 发布 TF odom → base_link ---
        tf_msg = TransformStamped()
        tf_msg.header.stamp = now.to_msg()
        tf_msg.header.frame_id = "odom"
        tf_msg.child_frame_id = "base_link"
        tf_msg.transform.translation.x = self.x
        tf_msg.transform.translation.y = self.y
        tf_msg.transform.translation.z = 0.0
        tf_msg.transform.rotation = _yaw_to_quat(self.theta)
        self.tf_broadcaster.sendTransform(tf_msg)

    def destroy_node(self):
        """销毁：停车 + 断开 CAN"""
        if self.car is not None:
            try:
                self.car.set_motion(linear=0.0, angular=0.0)
                self.car.close()
            except Exception:
                pass
        super().destroy_node()


def _yaw_to_quat(yaw: float) -> Quaternion:
    q = Quaternion()
    q.x = 0.0
    q.y = 0.0
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


def main(args=None):
    rclpy.init(args=args)
    node = ChassisNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("收到退出信号，正在停车...")
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
