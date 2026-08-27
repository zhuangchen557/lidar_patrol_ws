# FastAPI 机器人网关

网关位于 Vue 和 rosbridge 之间：

```text
Vue → FastAPI (:8000) → rosbridge (:9090) → ROS2 C++ 节点
```

FastAPI 不直接驱动电机。它订阅 ROS2 数据、转换网页协议、保存 SQLite
历史记录，并在鉴权后向 `/patrol/command` 发布高层命令。

## 本地启动

```powershell
cd gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

健康检查：`http://localhost:8000/api/health`

网页实时接口：`ws://localhost:8000/ws/robot`

## rosbridge

在 Ubuntu 22.04 + ROS2 Humble 机器人电脑运行：

```bash
sudo apt install ros-humble-rosbridge-server
source /opt/ros/humble/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

如果 FastAPI 和 rosbridge 不在同一台电脑，将 `.env` 中的
`ROSBRIDGE_URL` 改为机器人电脑的局域网地址，例如
`ws://192.168.31.100:9090`。

## 接口边界

- 传感器标量话题默认按 `std_msgs/msg/Float32` 的 `data` 字段解析。
- `/sensor/temp_hum` 兼容同时包含 `temperature`、`humidity` 的自定义消息。
- `/odom` 按 `nav_msgs/msg/Odometry` 解析。
- `/battery_state` 按 `sensor_msgs/msg/BatteryState` 解析。
- `/patrol/state` 按 `std_msgs/msg/String` 解析。
- `/patrol/command` 按 `std_msgs/msg/String` 发布高层巡检命令。

真实话题名称可通过 `.env` 修改，不需要改前端代码。

## 安全限制

- 密码只保存在 FastAPI 环境变量中，不写入 Vue。
- 当前控制只发布高层命令，不直接发布 `/cmd_vel`。
- “已提交”仅代表消息发给 rosbridge，不代表小车动作已完成。
- 正式控制还需要 ROS2 端的执行回执、限速、控制权互斥、硬件急停和断线停车。
