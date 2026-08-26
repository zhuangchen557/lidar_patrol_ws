# SLAM 建图模块

基于 LD06 激光雷达 + slam_toolbox 的推车建图方案。

## 系统架构

```
LD06 雷达 (/scan 变长点数)
       │
       ▼
  scan_repacker.py    ← 重采样至固定 360 点/帧，坏帧丢弃
       │
       ▼
  /scan_fixed (固定点数)
       │
       ├──────────────────┐
       ▼                  ▼
  slam_toolbox       静态 TF
  (纯扫描匹配)       odom→base_link
       │              (identity)
       ▼
  map→odom TF + /map
```

### 关键设计决策

**为什么不用 rf2o 里程计？**

rf2o 和 slam_toolbox 同时订阅 /scan_fixed 会产生 **TF 竞争**：rf2o 处理 scan 需要 30ms 才能发布 odom→base_link，但 slam 的 message filter 等不到就丢帧（"queue is full"）。解决方案是用静态 identity odom→base_link，让 slam 的扫描匹配器从零估计位姿。

**为什么需要 scan_repacker？**

usbipd 传输抖动导致 LD06 驱动的整圈拼包错乱，每帧点数在 84~542 之间跳变。slam_toolbox 以第一帧点数为基准，点数不匹配的帧直接拒收。repacker 重采样至固定 360 点，坏帧（<300 点）丢弃。

**走廊退化问题**

2D SLAM 在平行长墙的走廊中存在纵向退化——扫描匹配器无法区分"往前推了 0.5m"和"没动"，导致地图有重影。T 字路口提供横向约束，闭环后可校正漂移。地图可用于 Nav2 导航（AMCL 实时校正位姿）。

## 文件说明

### 脚本

| 文件 | 说明 |
|------|------|
| `scripts/handheld_mapping.sh` | **主入口**：启动推车建图全链路（雷达→repacker→slam），支持 `--stop` 停止 |
| `scripts/scan_repacker.py` | 扫描重打包节点：变长 /scan → 固定 360 点 /scan_fixed |
| `scripts/diag_push_test.sh` | 里程计诊断：推车 20 秒，自动判断 rf2o 是否跟得上运动 |
| `scripts/check_scan.sh` | 扫描流健康检查：统计点数分布和帧间隔抖动 |

### 配置

| 文件 | 说明 |
|------|------|
| `config/mapper_params_online_async.yaml` | slam_toolbox 参数（已针对推车建图调优） |
| `config/rf2o_params.yaml` | rf2o 激光里程计参数（诊断用，建图时不启用） |
| `config/amcl_params.yaml` | AMCL 定位参数 |
| `config/nav2_params.yaml` | Nav2 导航栈参数 |

### 地图

| 文件 | 说明 |
|------|------|
| `maps/my_map.pgm` | 实测走廊地图（23.3m × 20.2m，0.05m/pix） |
| `maps/my_map.yaml` | 地图元数据 |

## 快速开始

### 前置条件

- ROS2 Humble（Ubuntu 22.04）
- WSL2 + usbipd（Windows 侧挂载雷达 USB）
- 雷达设备节点：`/dev/wheeltec_lidar`（需 `usbipd attach --wsl`）

### 推车建图

```bash
# 1. 确认雷达已挂载
ls /dev/wheeltec_lidar

# 2. 启动建图
bash ~/slam_config/handheld_mapping.sh

# 3. 打开 RViz 查看
rviz2
# Fixed Frame = map
# Add: Map(/map) + LaserScan(/scan_fixed)

# 4. 匀速推车 <= 0.3m/s，走回起点闭环

# 5. 保存地图
ros2 run nav2_map_server map_saver_cli -f ~/my_map

# 6. 停止
bash ~/slam_config/handheld_mapping.sh --stop
```

### 诊断

```bash
# 扫描流健康检查（静止状态下运行）
bash ~/slam_config/check_scan.sh

# 推车里程计诊断（推车 20 秒）
bash ~/slam_config/diag_push_test.sh
```

## 已知限制

1. **USB 稳定性**：usbipd 传输抖动会导致偶发坏帧（repacker 已过滤）和帧间隔突变（~1s 停顿）
2. **走廊退化**：2D SLAM 在平行长墙走廊中纵向漂移，地图有重影
3. **无法转弯建图**：推车只能直线运动，无法走 S 形帮助横向约束

## 改进方向

- 物理层修复 USB 稳定性（扎紧线缆、缩短 USB 路径、用高质量 USB 线）
- 换用 cartographer SLAM（对退化场景更鲁棒）
- 集成 IMU 提供姿态约束
