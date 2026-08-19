# navigation：龚欣卉分工 B

## 已按当前项目接口设计

- ROS 2 Jazzy / Ubuntu 24.04
- `/odom`: `nav_msgs/Odometry`
- `/cmd_vel`: `geometry_msgs/Twist`
- waypoint：`map` 坐标
- waypoint yaw：弧度
- Nav2 Action：`/navigate_to_pose`
- rosbridge：9090
- `navigation` ROS2 package

## 真实路线录制

前提：底盘已经正常运行，并且 SLAM/定位已经提供稳定的 `map -> odom`，底盘提供 `odom -> base_link`。

```bash
ros2 run navigation waypoint_recorder \
  --ros-args \
  -p output_file:=routes/real_route.json \
  -p sample_interval:=2.0 \
  -p min_distance:=0.30
```

停止时 Ctrl+C，程序会保存 JSON。

## 路线校验

```bash
python3 navigation/route_validator.py routes/real_route.json
```

## Nav2 回放

确认 `/navigate_to_pose` 已经可用：

```bash
ros2 action list | grep navigate_to_pose
```

然后：

```bash
ros2 run navigation waypoint_player routes/real_route.json
```

## rosbridge

启动：

```bash
ros2 launch navigation navigation.launch.py
```

验证：

```bash
python3 navigation/rosbridge_client.py --topic /odom
```

## FastAPI

在 `navigation` 包目录附近执行：

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

## 注意

本包不自行实现 DWA/DWB。实际避障由你们最终 Nav2 配置负责。waypoint 只负责给 Nav2 发送目标点。

真实 waypoint 不直接把 `/odom` 的 x/y 当作最终路线坐标，而是通过 TF 获取 `map -> base_link`。
