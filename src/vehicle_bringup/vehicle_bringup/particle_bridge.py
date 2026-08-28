#!/usr/bin/env python3
"""AMCL 粒子云转换：/particle_cloud (nav2_msgs/ParticleCloud) -> /particlecloud (geometry_msgs/PoseArray)
RViz 的 rviz_default_plugins 无 ParticleCloud 插件，用 PoseArray 显示。
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseArray, Pose
from nav2_msgs.msg import ParticleCloud


class ParticleBridge(Node):
    def __init__(self):
        super().__init__("particle_bridge")
        self.sub = self.create_subscription(ParticleCloud, "/particle_cloud", self.cb, 10)
        self.pub = self.create_publisher(PoseArray, "/particlecloud", 10)
        self.get_logger().info("particle_bridge: /particle_cloud -> /particlecloud(PoseArray)")

    def cb(self, msg):
        out = PoseArray()
        out.header = msg.header
        out.header.frame_id = "map"
        out.poses = [Pose(pose=p.pose.position, orientation=p.pose.orientation) for p in msg.particles]
        self.pub.publish(out)


def main():
    rclpy.init()
    rclpy.spin(ParticleBridge())
    rclpy.shutdown()


if __name__ == "__main__":
    main()
