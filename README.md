# lidar_patrol_ws — 开发指南（dev 分支）

> 基于激光雷达的巡检车 · 上海泾研创智 · 生产实习项目一

---

## 团队成员与分支

| 成员 | 学号 | 职责 | 开发分支 | 模块 |
|------|------|------|----------|------|
| 胡祖宸 | 23121710 | 组长 · 底盘+集成 | `feature/chassis` | `vehicle_bringup` |
| 庄晨 | 23123435 | 后端 | `feature/lidar-slam` | `lidar_slam` |
| 龚欣卉 | 23121826 | 后端 | `feature/navigation` | `navigation` |
| 刘瑜彤 | 23121587 | 硬件 | `feature/sensor` | `sensor_bringup` |
| 周光玮 | 23123960 | 前端 | `feature/frontend` | `visualization` |

---

## 环境配置

### Ubuntu 24.04 安装 ROS2 Jazzy

```bash
# 1. 添加 ROS2 源
sudo apt update && sudo apt install software-properties-common curl -y
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 2. 安装
sudo apt update
sudo apt install ros-jazzy-desktop -y

# 3. 自动加载环境
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 安装编译工具和项目依赖

```bash
sudo apt install python3-colcon-common-extensions -y
sudo apt install ros-jazzy-slam-toolbox ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rosbridge-server -y
```

---

## 克隆仓库并创建分支

```bash
# 1. 克隆
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws

# 2. 切到 dev
git checkout dev

# 3. 创建自己的开发分支（每人选自己的那行）
git checkout -b feature/chassis      # 胡祖宸
git checkout -b feature/lidar-slam   # 庄晨
git checkout -b feature/navigation   # 龚欣卉
git checkout -b feature/sensor       # 刘瑜彤
git checkout -b feature/frontend     # 周光玮

# 4. 推送到远端
git push -u origin feature/<你的分支名>
```

---

## 创建自己的 ROS2 包

```bash
cd ~/lidar_patrol_ws/src

# 胡祖宸
ros2 pkg create --build-type ament_python vehicle_bringup

# 庄晨
ros2 pkg create --build-type ament_python lidar_slam
mkdir -p lidar_slam/lidar_slam lidar_slam/launch lidar_slam/config lidar_slam/maps

# 龚欣卉
ros2 pkg create --build-type ament_python navigation
mkdir -p navigation/navigation navigation/launch

# 刘瑜彤
ros2 pkg create --build-type ament_python sensor_bringup
mkdir -p sensor_bringup/sensor_bringup

# 周光玮
ros2 pkg create --build-type ament_python visualization
mkdir -p visualization/frontend


> 创建后在包目录下确保有 `__init__.py`（Python 包）和 `launch/` 目录。

---

## 每日开发流程

### 上午开工前（必须）

```bash
cd ~/lidar_patrol_ws
git checkout dev
git pull origin dev
git checkout feature/<你的分支名>
git merge dev
colcon build --symlink-install
source install/setup.bash
```

### 开发中

```bash
# 查看改动
git status
git diff

# 添加文件
git add src/<你的包名>/<文件>.py

# 提交
git commit -m "简短描述：做了什么"
```

### 每天收工前（必须）

```bash
git push
```

### 功能完成后 — 发起 PR

1. 浏览器打开 `https://github.com/zhuangchen557/lidar_patrol_ws`
2. 点 `Pull requests` → `New pull request`
3. base 选 **`dev`**，compare 选你的 **`feature/<分支名>`**
4. 标题格式：`[模块名] 做了什么`
5. 正文写明：改了什么、怎么测试、是否依赖其他人
6. 点 `Create pull request`，然后群里 @组长

---

## 目录结构

```
lidar_patrol_ws/
├── README.md
├── .gitignore
├── docs/
│   └── 接口规范.md           # ← 必读！
├── src/
│   ├── custom_interfaces/    # 共享消息（msg/SensorData.msg, msg/Waypoint.msg）
│   ├── vehicle_bringup/      # 胡祖宸：底盘控制 + 启动脚本
│   ├── lidar_slam/           # 庄晨：雷达 + SLAM + 定位
│   ├── navigation/           # 龚欣卉：避障 + waypoint + 后端 API
│   ├── sensor_bringup/       # 刘瑜彤：传感器驱动
│   └── visualization/        # 周光玮：Vue3 可视化前端
├── build/    (本地，已忽略)
├── install/  (本地，已忽略)
└── log/      (本地，已忽略)
```

---

## 注意事项

- **开发前必读**：[`docs/接口规范.md`](docs/接口规范.md)，所有 Topic 名称、消息格式、TF 坐标系以此为准
- 修改 `custom_interfaces/msg/*.msg` 后，**通知全员重新 `colcon build`**
- 每天收工前必须 `git push`，代码只存本地=白写
- `.gitignore` 已忽略 `build/` `install/` `log/` `__pycache__/`，不要把这些目录提交
- 编译后记得 `source install/setup.bash`，否则 ROS2 找不到你的包
- 遇到合并冲突解决不了，群里叫组长

---

## Git 速查表

| 操作 | 命令 |
|------|------|
| 看状态 | `git status` |
| 看改了啥 | `git diff` |
| 添加一个文件 | `git add <文件名>` |
| 添加全部改动 | `git add .` |
| 提交 | `git commit -m "描述"` |
| 推送 | `git push` |
| 拉最新 | `git pull` |
| 切换分支 | `git checkout <分支名>` |
| 看提交记录 | `git log --oneline -5` |
| 暂存改动（要临时切分支时） | `git stash` |
| 恢复暂存 | `git stash pop` |
| 放弃单个文件改动 | `git checkout -- <文件名>` |
| 看当前哪个分支 | `git branch` |

---

## 常见问题

**Q: `ros2` 命令找不到？**
A: `source /opt/ros/jazzy/setup.bash`，或检查 `~/.bashrc` 里有没有加这行。

**Q: `colcon build` 报错找不到某个包？**
A: 可能 `git pull dev` 漏了。执行 `git checkout dev && git pull && git checkout feature/<你的分支> && git merge dev`，再编译。

**Q: `ros2 interface show` 显示 Unknown package？**
A: 没 `source install/setup.bash`，或者是其他分支没建这个包。先 `colcon build` 再 `source`。

**Q: push 失败说 conflict？**
A: 别人改了你在改的同一个文件。先 `git pull origin dev`，合并冲突后 `git push`。

**Q: Git 要我输密码但总失败？**
A: 用 SSH 方式 clone，不要用 HTTPS。重新设置 remote：`git remote set-url origin git@github.com:zhuangchen557/lidar_patrol_ws.git`
