from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    route_file = LaunchConfiguration("route_file")

    return LaunchDescription([
        DeclareLaunchArgument(
            "route_file",
            default_value="",
            description="可选路线 JSON 文件"
        ),
        Node(
            package="rosbridge_server",
            executable="rosbridge_websocket",
            name="rosbridge_websocket",
            output="screen",
            parameters=[{"port": 9090}],
        ),
    ])
