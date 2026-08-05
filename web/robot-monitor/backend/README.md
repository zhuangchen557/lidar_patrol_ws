# C++ 模拟后端

这个后端用于在硬件和 ROS2 话题尚未就绪时验证网页通信。它每秒通过 `ws://localhost:8080/ws` 发送一条状态，并接受开始、暂停、停止三种任务命令。所有命令都只改变模拟状态，不会发布电机速度。

## Ubuntu 22.04 构建

```bash
sudo apt update
sudo apt install -y build-essential cmake git libboost-all-dev
cmake -S . -B build
cmake --build build -j
./build/robot_mock_backend
```

健康检查：`http://localhost:8080/api/health`

## 后续接入 ROS2

保留现有 WebSocket JSON 协议，把 `simulator_loop()` 替换为 `rclcpp` 订阅器：

- `/sensors/environment`：温度、湿度、CO、噪声
- `/odom`：x、y、yaw
- Nav2 Action：开始、暂停和停止巡检

真实底盘控制必须另外加入限速、急停、控制权互斥和断线停车；不要直接把当前模拟命令映射到电机。
