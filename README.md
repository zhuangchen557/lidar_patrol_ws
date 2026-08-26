# 基于激光雷达的巡检车

上海泾研创智 · 生产实习项目一

## 项目简介

基于开源巡检车底盘，集成激光雷达、温湿度传感器、噪声传感器，实现 SLAM 建图、自主导航、动态避障、定制路线巡检，环境数据实时上传至可视化监控平台。

## 技术栈

ROS2 Humble · Nav2 · SLAM Toolbox · LD06（激光雷达） · CAN 总线

## 项目结构

```
lidar_patrol_ws/
├── slam/               # SLAM 建图模块
│   ├── scripts/        # 建图脚本（scan_repacker、handheld_mapping 等）
│   ├── config/         # 参数文件（slam_toolbox、rf2o、amcl、nav2）
│   ├── maps/           # 实测地图
│   └── README.md       # 模块详细说明
├── YK_CANSDK/          # 底盘 CAN 通信 SDK（Python）
├── YK_CANSDK_CPP/      # 底盘 CAN 通信 SDK（C++）
└── docs/               # 项目文档
```

## 快速开始

### 推车建图

```bash
# 克隆仓库
git clone git@github.com:zhuangchen557/lidar_patrol_ws.git
cd lidar_patrol_ws

# 启动建图（需先挂载雷达 USB）
bash slam/scripts/handheld_mapping.sh

# 保存地图
ros2 run nav2_map_server map_saver_cli -f ~/my_map
```

详细说明见 [`slam/README.md`](slam/README.md)。

## 团队

| 成员 | 职责 |
|------|------|
| 胡祖宸 | 组长 · 底盘控制、Nav2 全局规划、系统集成 |
| 庄晨 | 后端 · 激光雷达驱动、SLAM 建图、AMCL 定位 |
| 龚欣卉 | 后端 · 动态避障、定制路线、FastAPI 后端 |
| 刘瑜彤 | 硬件 · 传感器采购安装、CAN 通信调试 |
| 周光玮 | 前端 · 可视化平台（Vue3 + ECharts） |

## 更多

- SLAM 建图：[`slam/README.md`](slam/README.md)
- 接口规范：[`docs/接口规范.md`](docs/接口规范.md)
- 项目方案：`docs/项目方案.md`
