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
    # 是否启动 Nav2 定位+导航栈（使用已保存地图时打开）
    use_nav2 = LaunchConfiguration("use_nav2", default="false")
    # 是否启动键盘遥控
    use_keyboard = LaunchConfiguration("use_keyboard", default="false")

    pkg_share = get_package_share_directory("vehicle_bringup")
    nav2_params_file = os.path.join(pkg_share, "config", "nav2_params.yaml")
    map_file = os.path.join(pkg_share, "config", "maps", "my_map.yaml")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_slam", default_value="false", description="启动 SLAM Toolbox 建图"),
            DeclareLaunchArgument("use_nav2", default_value="false", description="启动 map_server+AMCL+Nav2 导航"),
            DeclareLaunchArgument("map", default_value=map_file, description="地图 yaml 路径"),
            DeclareLaunchArgument("use_keyboard", default_value="false", description="启动键盘遥控节点"),

            # ============ 底盘控制（必须） ============
            Node(
                package="vehicle_bringup",
                executable="chassis_node",
                name="chassis_node",
                output="screen",
            ),

            # ============ 传感器桥（EnzoPatrolLab 网关快照 -> /sensor/* 标准话题） ============
            Node(
                package="vehicle_bringup",
                executable="sensor_bridge_node",
                name="sensor_bridge_node",
                output="screen",
            ),

            # ============ 激光雷达（LD19，串口 /dev/ttyUSB0） ============
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(
                    get_package_share_directory("ldlidar"), "launch", "ld19.launch.py")),
            ),

            # ============ /scan 双QoS转发（LD19 BEST_EFFORT -> RELIABLE，供 rosbridge/Windows 侧订阅） ============
            Node(
                package="vehicle_bringup",
                executable="scan_repub",
                name="scan_repub",
                output="screen",
            ),

            # ============ SLAM 建图（use_slam:=true 启动） ============
            # 链路: /scan → scan_repacker(重采样固定360点) → /scan_fixed → slam_toolbox
            # repacker 解决 usbipd 抖动导致 LD19 每帧点数不一致、slam_toolbox 拒帧的问题
            GroupAction(
                condition=IfCondition(use_slam),
                actions=[
                    Node(
                        package="vehicle_bringup",
                        executable="scan_repacker",
                        name="scan_repacker",
                        output="screen",
                        parameters=[{
                            "input_topic": "/scan",
                            "output_topic": "/scan_fixed",
                            "output_count": 360,
                            "min_input_points": 300,
                        }],
                    ),
                    Node(
                        package="slam_toolbox",
                        executable="async_slam_toolbox_node",
                        name="slam_toolbox",
                        output="screen",
                        parameters=[os.path.join(
                            get_package_share_directory("vehicle_bringup"),
                            "config", "mapper_params_online_async.yaml")],
                    ),
                ],
            ),

            # ============ Nav2 定位+导航（use_nav2:=true 启用，需已保存地图） ============
            GroupAction(
                condition=IfCondition(use_nav2),
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(os.path.join(
                            nav2_bringup_dir, "launch", "localization_launch.py")),
                        launch_arguments={
                            "map": map_file,
                            "params_file": nav2_params_file,
                            "use_sim_time": "false",
                            "autostart": "true",
                        }.items(),
                    ),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(os.path.join(
                            get_package_share_directory("vehicle_bringup"), "launch", "navigation_no_dock.launch.py")),
                        launch_arguments={
                            "params_file": nav2_params_file,
                            "use_sim_time": "false",
                            "autostart": "true",
                        }.items(),
                    ),
                ],
            ),

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

            # ============ rosbridge（WebSocket 桥接，EnzoPatrolLab 数据源） ============
            # 注意：必须在 scan_repub 之后启动，否则订阅 /scan 时报 topic 未广告
            Node(
                package="rosbridge_server",
                executable="rosbridge_websocket",
                name="rosbridge_websocket",
                output="screen",
                parameters=[{"port": 9090, "address": "127.0.0.1"}],
            ),

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
