"""一键启动巡检车全部节点"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # 是否启动 SLAM（正常巡检时关闭，建图时打开）
    use_slam = LaunchConfiguration("use_slam", default="false")
    # 是否启动键盘遥控
    use_keyboard = LaunchConfiguration("use_keyboard", default="false")

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_slam", default_value="false", description="启动 SLAM Toolbox 建图"),
            DeclareLaunchArgument("use_keyboard", default_value="false", description="启动键盘遥控节点"),

            # ============ 底盘控制（必须） ============
            Node(
                package="vehicle_bringup",
                executable="chassis_node",
                name="chassis_node",
                output="screen",
            ),

            # ============ 激光雷达（LD19，串口 /dev/ttyUSB0） ============
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(
                    get_package_share_directory("ldlidar"), "launch", "ld19.launch.py")),
            ),

            # ============ SLAM Toolbox 建图（传 use_slam:=true 启动） ============
            # Node(
            #     condition=IfCondition(use_slam),
            #     package="slam_toolbox",
            #     executable="async_slam_toolbox_node",
            #     name="slam_toolbox",
            #     output="screen",
            #     parameters=["/path/to/mapper_params.yaml"],
            # ),

            # ============ Nav2 导航栈（待调通底盘后启用） ============
            # IncludeLaunchDescription(
            #     PythonLaunchDescriptionSource([
            #         "/opt/ros/jazzy/share/nav2_bringup/launch/navigation_launch.py",
            #     ]),
            # ),

            # ============ 传感器节点（刘瑜彤负责，todo） ============
            # Node(
            #     package="sensor_bringup",
            #     executable="temp_hum_node",
            #     name="temp_hum_node",
            #     output="screen",
            # ),
            # Node(
            #     package="sensor_bringup",
            #     executable="noise_node",
            #     name="noise_node",
            #     output="screen",
            # ),

            # ============ rosbridge（龚欣卉负责，WebSocket 桥接） ============
            # Node(
            #     package="rosbridge_server",
            #     executable="rosbridge_websocket",
            #     name="rosbridge_websocket",
            #     output="screen",
            #     parameters=[{"port": 9090}],
            # ),

            # ============ 键盘遥控（调试用，传 use_keyboard:=true 启动） ============
            Node(
                condition=IfCondition(use_keyboard),
                package="teleop_twist_keyboard",
                executable="teleop_twist_keyboard",
                name="teleop_keyboard",
                output="screen",
                prefix="xterm -e",  # 需要 xterm 终端
            ),
        ]
    )
