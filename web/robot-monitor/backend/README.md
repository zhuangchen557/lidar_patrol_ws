# C++ 模拟后端

这个后端用于在硬件和 ROS2 话题尚未就绪时验证网页通信。它每秒通过 `ws://localhost:8080/ws` 发送状态，并接受开始、暂停、结束巡检和紧急停止命令。所有命令只改变模拟状态，不会发布电机速度。

## Ubuntu 22.04 构建

```bash
sudo apt update
sudo apt install -y build-essential cmake git libboost-all-dev
cmake -S . -B build
cmake --build build -j
export ROBOT_CONTROL_PASSWORD='请替换为小组控制密码'
./build/robot_mock_backend
```

健康检查：`http://localhost:8080/api/health`

如果没有设置 `ROBOT_CONTROL_PASSWORD`，监控数据仍然可查看，但真实控制无法解锁。不要把密码提交到 Git 或写入前端环境变量。

## WebSocket 协议

状态数据：

```json
{
  "type": "robot_status",
  "timestamp": 1786000000000,
  "source": "robot",
  "sensors": { "temperature": 25.6, "humidity": 58, "noise": 46 },
  "robot": { "online": true, "taskStatus": "待命", "battery": 87, "speed": 0 },
  "pose": { "x": 0, "y": 0, "yaw": 0 }
}
```

授权和控制：

```json
{ "type": "auth", "password": "由现场输入" }
{ "type": "command", "command": "start_patrol" }
{ "type": "lock" }
```

## 后续接入 ROS2

保留现有 WebSocket JSON 协议，把 `simulator_loop()` 替换为 `rclcpp` 订阅器：

- `/sensor/temp_hum`：温度、湿度
- `/sensor/noise`：噪声
- `/odom`：x、y、yaw
- Nav2 Action：开始、暂停和结束巡检

真实底盘控制必须另外加入限速、硬件急停、控制权互斥、命令审计和断线停车；不要直接把当前模拟命令映射到电机。
