#!/bin/bash
# 巡检车一键启动脚本（WSL 内执行）
# 用法: bash ~/lidar_patrol_ws/scripts/start_car.sh
# 前置: 已在 Windows 侧执行 usbipd attach 挂载雷达 USB（start_car.bat 自动完成）

set -e
cd ~/lidar_patrol_ws

echo "[1/4] 加载 USB 串口驱动 + 授权 /dev/ttyUSB0 ..."
sudo modprobe ch341 2>/dev/null || true
sleep 1
if [ -e /dev/ttyUSB0 ]; then
    sudo chmod 666 /dev/ttyUSB0
    echo "      /dev/ttyUSB0 已授权"
else
    echo "      警告: 未发现 /dev/ttyUSB0，请检查 usbipd attach 是否成功"
fi

echo "[2/4] 配置 WSL 网卡 IP (192.168.0.101, 连 CAN115) ..."
if ip addr show eth0 | grep -q '192.168.0.101'; then
    echo "      IP 已存在"
else
    sudo ip addr add 192.168.0.101/24 dev eth0
    echo "      已添加 192.168.0.101/24"
fi

echo "[3/4] 编译最新代码 ..."
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-skip yk_can_cpp robot_mock_backend 2>&1 | tail -3

echo "[4/4] 启动 bringup（底盘 + 雷达 + TF）... Ctrl+C 停止"
source install/setup.bash
ros2 launch src/vehicle_bringup/launch/bringup.launch.py