# lidar_patrol_ws — 开发分支

> **当前阶段：第1周（方案设计与环境搭建）**
>
> 下一周拿小车，第2周开始写代码。

## 环境配置

### 1. 安装 ROS2 Jazzy

Ubuntu 24.04 执行：

```bash
sudo apt update
sudo apt install software-properties-common -y
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
sudo apt install ros-jazzy-desktop -y
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 2. 安装编译工具和依赖

```bash
sudo apt install python3-colcon-common-extensions ros-jazzy-slam-toolbox ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server -y
```

### 3. 克隆仓库并加入开发

```bash
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws
git checkout dev

# 创建你自己的 feature 分支
git checkout -b feature/<你的模块名>
git push -u origin feature/<你的模块名>
```

### 4. 编译

```bash
colcon build --symlink-install
source install/setup.bash
```

## 分支策略

```
main  ←── 稳定版，仅 PR 合并
  ↑
 dev  ←── 日常开发集成
  ↑
feature/chassis    (胡祖宸：底盘)
feature/lidar-slam  (庄晨：雷达+SLAM)
feature/navigation  (龚欣卉：避障+路线)
feature/sensor      (刘瑜彤：传感器+CAN)
feature/frontend    (周光玮：可视化)
```

## 开发流程

1. 每天开工前：`git checkout dev && git pull origin dev && git checkout feature/<你的分支> && git merge dev`
2. 开发中：写代码 → `git add` → `git commit` → `git push`
3. 功能完成：在 GitHub 上发起 PR，base 选 `dev`，compare 选你的 `feature/<你的分支>`
4. 组长 Review 后合并

## 目录结构

```
src/
├── custom_interfaces/    # 共享消息（改此包需通知全员重新编译）
├── vehicle_bringup/      # 底盘控制 + 启动脚本（胡祖宸）
├── lidar_slam/           # 激光雷达 + SLAM + 定位（庄晨）
├── navigation/           # 避障 + 定制路线 + 后端 API（龚欣卉）
├── sensor_bringup/       # 传感器驱动（刘瑜彤）
└── visualization/        # 可视化前端（周光玮）
```

## 注意事项

- **必读**：[`docs/接口规范.md`](docs/接口规范.md)，所有 Topic、消息格式、TF 定义以此为准
- 修改 `custom_interfaces/msg/*.msg` 后，**通知全员重新 `colcon build`**
- 每天收工前 `git push`，避免代码丢失
- `.gitignore` 已忽略 `build/` `install/` `log/` `__pycache__/`，不要把这些目录提交进去
