# 基于激光雷达的巡检车

> 上海泾研创智 · 生产实习项目一 · ROS2 Jazzy

## 项目简介

基于开源巡检车底盘，集成激光雷达与环境传感器（温湿度、噪声），实现SLAM建图、自主导航、动态避障、定制路线巡检，环境数据实时上传至可视化平台。

## 环境要求

| 组件 | 版本 |
|------|------|
| 操作系统 | Ubuntu 22.04 / 24.04 |
| ROS2 | Jazzy Jalisco |
| Python | 3.10+ |

## 快速开始

### 1. 安装依赖

```bash
# ROS2 Jazzy（如未安装）
# 参考：https://docs.ros.org/en/jazzy/Installation.html

# 安装 colcon 编译工具
sudo apt install python3-colcon-common-extensions -y

# 安装项目依赖的 ROS2 包
sudo apt install ros-jazzy-slam-toolbox ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server -y
```

### 2. 克隆仓库

```bash
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws
git checkout dev
```

### 3. 编译

```bash
colcon build --symlink-install
source install/setup.bash
```

### 4. 启动

```bash
ros2 launch vehicle_bringup bringup.launch.py
```

## 目录结构

```
lidar_patrol_ws/
├── README.md
├── docs/
│   └── 接口规范.md           # ROS2 Topic/TF/消息格式定义（必读）
├── src/
│   ├── custom_interfaces/    # 共享自定义消息
│   │   ├── msg/
│   │   │   ├── SensorData.msg
│   │   │   └── Waypoint.msg
│   ├── vehicle_bringup/      # 底盘控制 + 启动脚本（组长）
│   ├── lidar_slam/           # 激光雷达 + SLAM + 定位（庄晨）
│   ├── navigation/           # 避障 + 定制路线 + 后端（龚欣卉）
│   ├── sensor_bringup/       # 传感器驱动（刘瑜彤）
│   └── visualization/        # 可视化前端（成员D）
├── .gitignore
└── requirements.txt
```

## 分支策略

| 分支 | 用途 |
|------|------|
| `main` | 稳定版本，仅通过 PR 合并 |
| `dev` | 日常开发集成 |
| `feature/chassis` | 底盘控制（胡祖宸） |
| `feature/lidar-slam` | 雷达+SLAM（庄晨） |
| `feature/navigation` | 避障+路线（龚欣卉） |
| `feature/sensor` | 传感器+CAN（刘瑜彤） |
| `feature/frontend` | 可视化（成员D） |

## 开发流程

1. 从 `dev` 拉出自己的 `feature/*` 分支
2. 在自己的分支上开发
3. 功能完成后发起 PR 到 `dev`
4. 组长 Review 后合并
5. 阶段完成后 `dev` 合入 `main`

## 接口规范

所有 Topic、消息格式、TF 坐标系定义见 [`docs/接口规范.md`](docs/接口规范.md)，开发前必须阅读。

## 团队

| 成员 | 职责 |
|------|------|
| 胡祖宸 | 组长：底盘控制、Nav2全局规划、系统集成 |
| 庄晨 | 后端：激光雷达驱动、SLAM建图、AMCL定位 |
| 龚欣卉 | 后端：避障、定制路线、FastAPI后端 |
| 刘瑜彤 | 硬件：传感器采购安装、CAN通信 |
| 成员D | 前端：可视化平台 |
