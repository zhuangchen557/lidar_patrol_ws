# 巡检车项目 — 快速开始

> 基于激光雷达的巡检车 · 上海泾研创智 · 生产实习项目一

---

## 一键启动（推荐）

### 前置条件
- Windows 11 + WSL2 Ubuntu 24.04
- ROS2 Jazzy 已安装（见下方环境安装）
- 激光雷达 USB 已插入电脑

### 启动步骤

**1. 管理员 PowerShell 挂载雷达 USB：**
```powershell
usbipd attach --wsl Ubuntu --busid 1-10
```

**2. 双击运行：**
```
docs/start_car.bat
```
自动完成：清理旧转发器 -> 起 TCP 转发器 -> 挂载雷达 -> 编译 -> 启动底盘+雷达+TF

**3. 键盘遥控（新终端）：**
```bash
cd ~/lidar_patrol_ws && source install/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
# i=前进  ,=后退  j=左转  l=右转  k=停
```

---

## 完整操作指南

详细说明请看：**[docs/快速启动指南.md](docs/快速启动指南.md)**

包含：手动分步启动、RViz 可视化、避障测试、路线录制回放、排错指南

---

## 环境安装

### 1. 安装 ROS2 Jazzy
```bash
sudo apt update && sudo apt install software-properties-common curl -y
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update && sudo apt install ros-jazzy-desktop -y
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

### 2. 安装项目依赖
```bash
sudo apt install python3-colcon-common-extensions -y
sudo apt install ros-jazzy-slam-toolbox ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server -y
```

### 3. 克隆仓库
```bash
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws
git checkout dev
colcon build --symlink-install
source install/setup.bash
```

---

## SLAM 建图
```bash
# 挂载雷达后（见一键启动步骤1）
cd ~/lidar_patrol_ws && source install/setup.bash
ros2 launch vehicle_bringup bringup.launch.py use_slam:=true
# 推车走一圈建图，完成后保存：
ros2 run nav2_map_server map_saver_cli -f ~/my_map
```

详细说明：[slam/README.md](slam/README.md)

---

## 导航避障
```bash
ros2 launch vehicle_bringup bringup.launch.py use_nav2:=true
# RViz 里 2D Pose Estimate 定位 -> 发 Nav2 Goal 导航
```

---

## 路线巡检
```bash
# 录制路线
ros2 run navigation waypoint_recorder routes/my_route.json map_frame:=odom
# 回放（直接控制）
ros2 run navigation waypoint_player routes/my_route.json --ros-args -p use_nav2:=false
```

---

## 可视化监控

### RViz2（WSL 内）
```bash
rviz2
# Fixed Frame -> base_laser -> Add -> /scan (LaserScan) + TF
```

### EnzoPatrolLab 实验台（Windows）
双击 `Enzo巡迹实验台.exe`，实时显示传感器数据+雷达扫描+轨迹

### Web 监控平台
```bash
cd web/robot-monitor
npm install && npm run dev
```

---

## 项目结构

```
lidar_patrol_ws/
├── src/
│   ├── vehicle_bringup/     # F1 底盘控制 + F2 雷达驱动
│   ├── lidar_avoidance/     # F4 避障
│   ├── navigation/          # F5 路线巡检
│   └── vehicle_bringup/     # F3 SLAM / F4 Nav2 集成
├── slam/                    # SLAM 建图模块
├── web/robot-monitor/       # F7 可视化前端
├── scripts/                 # 标定脚本、转发器
├── docs/                    # 快速启动指南、应用指南、接口规范
└── YK_CANSDK/               # 底盘 CAN SDK
```

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [docs/快速启动指南.md](docs/快速启动指南.md) | **安装部署、一键启动、手动排错** |
| [docs/应用指南.md](docs/应用指南.md) | 架构、功能、标定、参数、排坑 |
| [docs/接口规范.md](docs/接口规范.md) | Topic、消息格式、TF 坐标系 |
| [slam/README.md](slam/README.md) | SLAM 建图详细说明 |
| [web/robot-monitor/README.md](web/robot-monitor/README.md) | Web 监控平台 |

---

## 团队

| 成员 | 职责 | 模块 |
|------|------|------|
| 胡祖宸 | 组长 - 底盘+集成 | vehicle_bringup |
| 庄晨 | 雷达+SLAM | lidar_slam |
| 龚欣卉 | 避障+路线+后端 | navigation |
| 刘瑜彤 | 硬件+传感器 | sensor_bringup |
| 周光玮 | 前端可视化 | web/robot-monitor |

---

## 常见问题

**Q: chassis_node 报 Connection refused？**
A: 转发器没起。跑 `python docs/forward_5578.py`

**Q: 雷达 /dev/ttyUSB0 不存在？**
A: `usbipd attach --wsl Ubuntu --busid 1-10` + `sudo modprobe ch341 && sudo chmod 666 /dev/ttyUSB0`

**Q: 地面转弯无力？**
A: MAX_ANGULAR_SPEED=16 是悬空标定值，需跑落地旋转标定：`python3 scripts/recalibrate_rot.py`

**Q: ros2 命令找不到？**
A: `source /opt/ros/jazzy/setup.bash`

**Q: colcon build 报错？**
A: `git checkout dev && git pull && git checkout feature/<你的分支> && git merge dev` 再编译
