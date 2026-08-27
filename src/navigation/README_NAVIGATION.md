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


## 新增：沿已录制路线返回原点

如果已经完成一条真实路线录制，并且当前小车位于路线终点，可以让 Nav2 按照录制点的**逆序**返回第一个 waypoint（即录制原点）：

```bash
ros2 run navigation return_to_origin routes/real_route.json
```

默认会跳过当前最后一个 waypoint，避免机器人已经在终点时重复发送一次相同目标，然后依次执行倒数第二个点……最后到第一个点。

如需严格把最后一个 waypoint 也重新发送：

```bash
ros2 run navigation return_to_origin routes/real_route.json \
  --ros-args -p skip_current_point:=false
```

前提：
- 路线 JSON 的 `frame_id` 必须是 `map`；
- Nav2 `/navigate_to_pose` 必须已经启动；
- `map -> odom -> base_link` TF 正常；
- 机器人当前环境应与录制路线的地图基本一致。

注意：这里的“回退”是**沿原路线的 waypoint 逆序导航**，不是让底盘倒车（reverse driving）。机器人仍由 Nav2 正常朝向每个 waypoint 行驶，因此可以利用规划器和避障能力。
