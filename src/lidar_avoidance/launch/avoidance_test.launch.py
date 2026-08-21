from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='lidar_avoidance',
            executable='laser_avoidance',
            name='laser_avoidance',
            output='screen',
            parameters=[{
                'scan_topic': '/scan',
                'cmd_vel_topic': '/cmd_vel',
                'safe_distance': 1.0,
                'stop_distance': 0.50,
                'forward_speed': 0.20,
                'slow_speed': 0.10,
                'turn_speed': 0.55,
            }],
        ),
    ])
