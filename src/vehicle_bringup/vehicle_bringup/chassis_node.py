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
MAX_LINEAR_SPEED = 0.5       # 最大线速度 m/s（需要实测校准）
MAX_ANGULAR_SPEED = 1.0      # 最大角速度 rad/s（需要实测校准）
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

            config = VehicleConfig()
            self.car = FourWheelVehicle(config)
            self.get_logger().info("YK_CAN SDK 已加载")
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

    def cmd_callback(self, msg: Twist):
        """接收 /cmd_vel 指令 → 调用 set_motion"""
        self.last_cmd_time = self.get_clock().now()
        self.last_cmd_linear = msg.linear.x
        self.last_cmd_angular = msg.angular.z

        if self.car is not None:
            try:
                self.car.set_motion(
                    linear=msg.linear.x,
                    angular=msg.angular.z,
                )
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

        # --- 根据最近一次 /cmd_vel 推算位姿 ---
        vx = self.last_cmd_linear * MAX_LINEAR_SPEED
        vth = self.last_cmd_angular * MAX_ANGULAR_SPEED

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
