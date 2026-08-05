# 基于激光雷达的巡检车

上海泾研创智 · 生产实习项目一

## 项目目标

基于开源巡检车底盘，集成激光雷达、温湿度传感器、噪声传感器，实现：
- 激光雷达 SLAM 建图
- 自主导航与动态避障
- 定制路线巡检（录制 + 回放）
- 环境数据可视化监控平台

## 技术栈

- **ROS2** Jazzy（Ubuntu 24.04）
- **导航** Nav2 + SLAM Toolbox
- **底盘** YK_CAN SDK（USR-CAN115 + 南京运康驱动器）
- **可视化** Vue3 + ECharts + FastAPI + SQLite
- **激光雷达** RPLIDAR A1

## 快速开始

```bash
# 安装依赖
sudo apt install ros-jazzy-slam-toolbox ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server python3-colcon-common-extensions -y

# 克隆
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws

# 编译
colcon build --symlink-install
source install/setup.bash
```

## 目录结构

```
src/
├── custom_interfaces/    # 共享消息定义（SensorData.msg, Waypoint.msg）
├── vehicle_bringup/      # 底盘控制 + 启动脚本
├── lidar_slam/           # 激光雷达 + SLAM + 定位
├── navigation/           # 避障 + 定制路线 + 后端 API
├── sensor_bringup/       # 传感器驱动
└── visualization/        # 可视化前端
```

## 开发规范

- 接口规范见 [`docs/接口规范.md`](docs/接口规范.md)
- 从 `dev` 拉出 `feature/<模块名>` 分支开发
- 完成后提交 PR 到 `dev`

## 团队

| 成员 | 职责 |
|------|------|
| 胡祖宸 | 组长 · 底盘控制、Nav2全局规划、系统集成 |
| 庄晨 | 后端 · 激光雷达驱动、SLAM建图、AMCL定位 |
| 龚欣卉 | 后端 · 动态避障、定制路线、FastAPI后端 |
| 刘瑜彤 | 硬件 · 传感器采购安装、CAN通信调试 |
| 周光玮 | 前端 · 可视化平台（Vue3+ECharts） |
