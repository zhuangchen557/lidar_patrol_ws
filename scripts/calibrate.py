#!/usr/bin/env python3
"""底盘标定辅助脚本 v2：闭环走固定 1 米 / 原地转 1 圈，量实际值计算新参数"""
import math
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

MAX_LINEAR_SPEED = 0.5
MAX_ANGULAR_SPEED = 1.0
TARGET_DIST = 1.0    # 直线目标：odom 走 1 米
TARGET_TURNS = 1.0   # 旋转目标：odom 转 1 圈
CMD_LINEAR = 0.5     # 直线指令 m/s（归一化后满速）
CMD_ANGULAR = 1.0    # 旋转指令 rad/s（归一化后满速）


class Calibrator(Node):
    def __init__(self):
        super().__init__('chassis_calibrator')
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.odom_sub = self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.odom = None

    def odom_cb(self, msg: Odometry):
        self.odom = msg

    def publish_cmd(self, linear, angular):
        cmd = Twist()
        cmd.linear.x = linear
        cmd.angular.z = angular
        self.cmd_pub.publish(cmd)

    def stop(self):
        for _ in range(10):
            self.publish_cmd(0.0, 0.0)
            time.sleep(0.05)

    def spin_wait(self, timeout_s=0.2):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.01)

    def get_yaw(self):
        if self.odom is None:
            return None
        p = self.odom.pose.pose.orientation
        return 2.0 * math.atan2(p.z, p.w)

    def drive_1m(self):
        """闭环前进：odom 位移达到 1 米自动停"""
        print('>>> 车开始前进，走到 odom 1 米自动停', flush=True)
        if self.odom is None:
            print('错误：无 odom')
            return None
        start_x = self.odom.pose.pose.position.x
        while self.odom is not None:
            rclpy.spin_once(self, timeout_sec=0.02)
            self.publish_cmd(CMD_LINEAR, 0.0)
            dx = self.odom.pose.pose.position.x - start_x
            if dx >= TARGET_DIST:
                break
            time.sleep(0.005)
        self.stop()
        return start_x

    def spin_1turn(self):
        """闭环旋转：odom 转满 1 圈自动停"""
        print('>>> 车开始原地旋转，转满 1 圈自动停', flush=True)
        if self.odom is None:
            print('错误：无 odom')
            return None
        last = self.get_yaw()
        accum = 0.0
        while self.odom is not None:
            rclpy.spin_once(self, timeout_sec=0.02)
            self.publish_cmd(0.0, CMD_ANGULAR)
            yaw = self.get_yaw()
            if yaw is None:
                continue
            d = yaw - last
            if d > math.pi:
                d -= math.tau
            elif d < -math.pi:
                d += math.tau
            accum += d
            last = yaw
            if accum >= math.tau * TARGET_TURNS:
                break
            time.sleep(0.005)
        self.stop()
        return accum

    def calibrate_linear(self):
        print('== 直线标定：车将自动走 1 米 ==', flush=True)
        input('>>> 地面放好卷尺（起点对车头），按回车开始')
        self.drive_1m()
        actual = float(input('>>> 卷尺量：车实际走了多少米（如 0.95、1.1）: '))
        factor = actual / TARGET_DIST
        new_max = MAX_LINEAR_SPEED * factor
        print('实际 %.3f m / 目标 1 m -> 修正系数 %.3f，新 MAX_LINEAR_SPEED = %.3f' % (actual, factor, new_max))
        return new_max

    def calibrate_angular(self):
        print('== 旋转标定：车将自动原地转 1 圈 ==', flush=True)
        input('>>> 在车头方向放一个参照物（观察转了几圈），按回车开始')
        self.spin_1turn()
        turns = float(input('>>> 车实际转了多少圈（如 0.9、1.2）: '))
        factor = turns / TARGET_TURNS
        new_max = MAX_ANGULAR_SPEED * factor
        print('实际 %.3f 圈 / 目标 1 圈 -> 修正系数 %.3f，新 MAX_ANGULAR_SPEED = %.3f' % (turns, factor, new_max))
        return new_max


    def calibrate_linear_count(self, wheel_radius=0.16):
            """直线标定（悬空数圈法）：满速空转 5 秒，数轮子圈数
            轮子周长 = 2*pi*r，1 米 = 1/(2*pi*r) 圈"""
            circ = math.tau * wheel_radius
            dur = 5.0
            print('== 直线标定（数圈法）==', flush=True)
            print('>>> 车将满速空转 %.1f 秒（轮子周长 %.3f m）' % (dur, circ), flush=True)
            input('>>> 在轮子上贴好胶带标记，按回车开始')
            t0 = time.time()
            while time.time() - t0 < dur:
                self.publish_cmd(CMD_LINEAR, 0.0)
                time.sleep(0.02)
            self.stop()
            turns = float(input('>>> 数：5 秒内轮子实际转了多少圈（如 4.2、5.1）: '))
            speed = turns * circ / dur
            print('实际线速度 %.3f m/s，新 MAX_LINEAR_SPEED = %.3f' % (speed, speed))
            return speed
    
    
def main():
    import sys
    rot_only = '--rot-only' in sys.argv
    lin_count = '--lin-count' in sys.argv
    rclpy.init()
    node = Calibrator()
    print('等待 /odom 数据...', flush=True)
    t0 = time.time()
    while node.odom is None and time.time() - t0 < 10:
        rclpy.spin_once(node, timeout_sec=0.5)
    if node.odom is None:
        print('错误：10 秒内未收到 /odom，请确认 bringup（chassis_node）在运行！')
        rclpy.shutdown()
        return
    print('已连接底盘。', flush=True)

    if rot_only:
        na = node.calibrate_angular()
        print('')
        print('========== 旋转标定结果 ==========')
        print('MAX_ANGULAR_SPEED = %.3f' % na)
        print('==================================')
    elif lin_count:
        nl = node.calibrate_linear_count()
        print('')
        print('========== 直线标定结果 ==========')
        print('MAX_LINEAR_SPEED = %.3f' % nl)
        print('==================================')
    else:
        nl = node.calibrate_linear()
        na = node.calibrate_angular()
        print('')
        print('========== 标定结果 ==========')
        print('MAX_LINEAR_SPEED  = %.3f' % nl)
        print('MAX_ANGULAR_SPEED = %.3f' % na)
        print('==============================')
    rclpy.shutdown()


if __name__ == '__main__':
    main()
