# lidar_patrol_ws — 基于激光雷达的巡检车

基于 **激光雷达 + ROS2** 的自主巡检小车完整工程。上海泾研创智生产实习项目（2026.8），
包含底盘控制、SLAM 建图、Nav2 导航避障、路线巡检、环境传感器、可视化监控与报警全链路。

**克隆本仓库即可运行整个系统**（含 EnzoPatrolLab 实验台完整包）。

---

## 功能一览（F1-F8）

| 模块 | 功能 | 状态 |
|------|------|------|
| F1 | 底盘运动控制（CAN115 + 自动重连/心跳） | ✅ 实车验证 |
| F2 | LD19 雷达驱动与 360° 点云 | ✅ 实车验证 |
| F3 | SLAM 建图（slam_toolbox） | ✅ 已建图（my_map.pgm） |
| F4 | Nav2 自主导航 + 激光避障 | ✅ 导航全栈 / 避障实车验证 |
| F5 | 定制路线巡检（录制/回放/回原点） | ✅ 实车验证（回放带自动避障） |
| F6 | 温湿度传感器集成 | ✅ 实车验证 |
| F7 | EnzoPatrolLab 可视化平台（雷达/传感器/轨迹） | ✅ 实车验证 |
| F8 | 异常报警（阈值弹窗/列表） | ✅ |

---

## 目录结构

```
lidar_patrol_ws/
├── src/                       # ROS2 源码包
│   ├── vehicle_bringup/       # F1 底盘 + F2 雷达集成 + Nav2/SLAM 启动
│   ├── lidar_avoidance/       # F4 激光避障（FORWARD/SLOW/TURN 状态机）
│   ├── navigation/            # F5 路线录制/回放（含避障）/ 后端
│   ├── ldlidar/               # LD19 雷达驱动（ROS2 Jazzy）
│   └── custom_interfaces/     # 自定义消息
├── YK_CANSDK/                 # 底盘 CAN SDK（Python）
├── web/robot-monitor/         # F7 Web 前端 + 网关
│   └── gateway-ros2/          # 实验台网关源码（rosbridge 版，替代编译版 exe）
├── slam/                      # F3 建图配置与地图（my_map.pgm）
├── EnzoPatrolLab/             # F7/F8 Windows 实验台完整包（0.2.0，Git LFS）
├── scripts/                   # 转发器 / 一键启动 / 标定脚本
├── config/                    # RViz 配置（nav2.rviz）
└── docs/                      # 快速启动指南 / 应用指南 / 接口规范
```

---

## 环境要求

| 项 | 要求 |
|----|------|
| 操作系统 | Windows 11（+ WSL2） |
| WSL 发行版 | Ubuntu 24.04 |
| ROS2 | Jazzy（Desktop 版） |
| 底盘 | 四轮差速底盘 + CAN115 网关（192.168.0.7:5578） |
| 雷达 | LD19 单线激光雷达（USB CH340，/dev/ttyUSB0） |
| 传感器 | LES11B 温湿度（USB Modbus RTU 9600） |

---

## 一、环境安装（新电脑）

### 1. Windows 侧
```powershell
# 启用 WSL2（管理员 PowerShell）
wsl --install -d Ubuntu-24.04

# 安装 usbipd（USB 设备共享到 WSL）
winget install usbipd

# 安装 Python（转发器/网关需要）
# https://www.python.org/downloads/  安装后加入 PATH
```

### 2. WSL 侧（Ubuntu 24.04）
```bash
# ROS2 Jazzy
sudo apt update && sudo apt install software-properties-common curl -y
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update && sudo apt install ros-jazzy-desktop -y
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc

# 依赖
sudo apt install -y python3-colcon-common-extensions ros-jazzy-slam-toolbox ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server git-lfs tmux

# ROS2 局域网发现（WSL 环境必备，解决 DDS 跨进程发现失败）
echo "export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST" >> ~/.bashrc
echo "export ROS_LOCALHOST_ONLY=1" >> ~/.bashrc
source ~/.bashrc
```

### 3. 克隆并编译
```bash
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws
git lfs pull                # 拉取 EnzoPatrolLab 大文件
colcon build --symlink-install --packages-skip yk_can_cpp
source install/setup.bash
```

### 4. Windows 侧 Python 依赖（EnzoPatrolLab 网关用）
```powershell
pip install fastapi "uvicorn[standard]" pyserial websocket-client
```

---

## 二、快速启动

### 方式 A：一键启动（推荐）
1. 雷达 USB 插电脑 → 管理员 PowerShell：
   ```powershell
   usbipd list                       # 找到 USB-SERIAL CH340 的 busid（如 1-10）
   usbipd attach --wsl Ubuntu --busid <busid>
   ```
2. 网线连接：CAN115(192.168.0.7) ←→ 电脑网口；管理员运行 `scripts/fix_can115.bat`（设 IP 192.168.0.100/24）
3. 双击 `docs/start_car.bat`（自动：转发器 → 雷达挂载 → 编译 → 启动底盘+雷达+repub+rosbridge）
4. 键盘遥控（WSL 新终端）：
   ```bash
   ros2 run teleop_twist_keyboard teleop_twist_keyboard   # i前进 ,后退 j/l转向 k停
   ```

### 方式 B：手动分步
```bash
# 1. Windows：起转发器（127.0.0.1:5578 -> CAN115）
python scripts/forward_5578.py

# 2. WSL：启动整车（底盘 + 雷达 + TF + repub + rosbridge）
cd ~/lidar_patrol_ws && source install/setup.bash
ros2 launch vehicle_bringup bringup.launch.py
```

---

## 三、功能使用

### 导航（Nav2，使用 my_map.pgm）
```bash
ros2 launch vehicle_bringup bringup.launch.py use_nav2:=true
rviz2 -d config/nav2.rviz        # 地图/点云/粒子/位姿自动显示
```
- 定位：RViz 工具栏 **2D Pose Estimate** 点车实际位置
- 导航：**2D Goal Pose** 点目标点
- 命令行发目标：`ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose '{pose: {header: {frame_id: "map"}, pose: {position: {x: 1.0, y: 0.0}, orientation: {w: 1.0}}}}'`

### 避障（独立测试）
```bash
ros2 run lidar_avoidance laser_avoidance
# 前方<0.5m 或侧向<0.3m 触发 TURN 避让；参数在 src/lidar_avoidance/config/avoidance.yaml
```

### 路线巡检（录制/回放）
```bash
# 录制（键盘遥控走一遍，Ctrl+C 保存）
ros2 run navigation waypoint_recorder --ros-args -p output_file:=src/navigation/routes/patrol_route.json -p map_frame:=odom
# 回放（直控模式，带自动避障：障碍<0.5m 停车等待）
ros2 run navigation waypoint_player src/navigation/routes/patrol_route.json --ros-args -p use_nav2:=false -p map_frame:=odom -p dwell_seconds:=2.0
```

### 落地旋转标定（换底盘必做）
```bash
ros2 run vehicle_bringup chassis_node        # 只起底盘
python3 scripts/recalibrate_rot.py           # 满速转 4 秒数圈
# 结果写回 src/vehicle_bringup/vehicle_bringup/chassis_node.py 的 MAX_ANGULAR_SPEED
```

### EnzoPatrolLab 实验台（Windows）
```
双击 EnzoPatrolLab/Enzo巡迹实验台.exe
```
- 显示：雷达点云 + 温湿度 + 底盘状态 + 轨迹 + 报警
- 雷达数据通过 rosbridge 从 WSL `/scan` 获取（雷达 USB 归 WSL）
- 前置：WSL 内 bringup 已含 scan_repub + rosbridge
- 温湿度：USB 插电脑，experiment-config.json 里 `usbSensor.port` 设实际 COM 口
- 网关为 rosbridge 版：若 exe 内网关异常，可源码运行
  `web/robot-monitor/gateway-ros2/`（见其 README）

---

## 四、关键架构说明

```
雷达USB → WSL(ldlidar → /scan BEST_EFFORT)
  → scan_repub(双QoS转发 RELIABLE) → /scan
  → 避障/Nav2(RELIABLE订阅) + rosbridge_server(9090)
  → EnzoPatrolLab gateway-ros2 → 前端雷达图

底盘CAN115(192.168.0.7) ←网线→ Windows网口(192.168.0.100)
  → forward_5578.py(127.0.0.1:5578) → WSL chassis_node → /cmd_vel /odom

温湿度USB(COM3) → EnzoPatrolLab gateway(Modbus RTU) → 前端 + /sensor/*(sensor_bridge_node)
```

### 已标定参数（chassis_node.py）
| 参数 | 值 | 说明 |
|------|-----|------|
| MAX_LINEAR_SPEED | 1.257 m/s | 满速直线实测 |
| MAX_ANGULAR_SPEED | 1.67 rad/s | 满速实际 1.26 rad/s；<30% 出力有死区 |
| WHEEL_BASE | 0.35 m | 待实测修正 |

### 避障参数（avoidance.yaml）
| 参数 | 值 | 说明 |
|------|-----|------|
| stop_distance | 0.50 m | 前方停车距离 |
| side_stop_distance | 0.30 m | 侧向避障触发（独立） |
| safe_distance / side_safe_distance | 1.0 / 0.30 m | 减速触发 |

### Nav2 参数（nav2_params.yaml）
- 地图：`config/maps/my_map.pgm`（0.05m/格，origin [-10.2, -5.69]）
- footprint：0.30×0.30m；inflation_radius：0.3m
- AMCL 仅配置 `base_frame_id: base_link`（完整段会破坏 map 订阅，勿改）

---

## 五、文档

| 文档 | 内容 |
|------|------|
| [docs/快速启动指南.md](docs/快速启动指南.md) | 启动/排错/日常命令 |
| [docs/应用指南.md](docs/应用指南.md) | 架构/标定/参数/排坑 |
| [docs/接口规范.md](docs/接口规范.md) | 话题/消息/TF 规范 |
| [web/robot-monitor/gateway-ros2/README.md](web/robot-monitor/gateway-ros2/README.md) | 实验台网关部署 |
| EnzoPatrolLab/实验版使用说明.md | 实验台使用 |

---

## 六、常见问题

| 现象 | 解决 |
|------|------|
| 底盘连不上 / Connection refused | 转发器没起或 CAN115 网卡 IP 丢了：`fix_can115.bat` |
| 雷达 /dev/ttyUSB0 不存在 | `usbipd list` 找 busid → attach → `sudo modprobe ch341 && sudo chmod 666 /dev/ttyUSB0` |
| RViz 收不到话题 | 确认 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` 已生效（所有终端 source ~/.bashrc） |
| EnzoPatrolLab 雷达无数据 | 重启实验台；确认 WSL 内 rosbridge 在跑（bringup 自带） |
| colcon 卡死 | 不要同时开两个 start_car.bat；`pkill -f colcon` 后重试 |
| 避障不转向 | 检查 MAX_ANGULAR_SPEED（<30% 出力死区） |

---

## 七、团队

| 成员 | 职责 |
|------|------|
| 胡祖宸 | 组长 · 底盘控制 + 系统集成 |
| 庄晨 | 雷达 + SLAM 建图 |
| 龚欣卉 | 避障 + 路线巡检 + 后端 |
| 刘瑜彤 | 硬件 + 传感器 |
| 周光玮 | 可视化前端（robot-monitor） |

---

## 八、Git 协作规范

- 主分支：`main`（发布） / `dev`（集成） / `feature/*`（个人开发）
- 开发流程：`git checkout dev && git pull && git checkout -b feature/xxx` → 开发 → PR 到 dev
- 大文件（exe/dll）走 Git LFS：`git lfs pull` 拉取
