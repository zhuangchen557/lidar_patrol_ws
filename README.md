# feature/chassis — 底盘控制与系统集成

胡祖宸 开发分支

## 功能

本分支负责小车的底层运动控制和系统整体集成：

- 将 YK_CAN SDK 封装为 ROS2 节点，接收 `/cmd_vel` 话题控制车轮
- 发布 `/odom` 里程计话题
- 配置 TF 树（odom → base_link）
- 配置 Nav2 全局规划器
- 编写全系统启动脚本 `bringup.launch.py`

## 依赖

- `custom_interfaces`（共享消息）
- YK_CAN SDK（公司提供，TCP 连接 USR-CAN115，IP=192.168.0.7）

## 接口

本分支发布/订阅的 ROS2 接口：

| 方向 | Topic | 消息类型 | 说明 |
|------|-------|----------|------|
| 订阅 | `/cmd_vel` | `geometry_msgs/Twist` | 接收速度指令 |
| 发布 | `/odom` | `nav_msgs/Odometry` | 发布里程计 |
| TF | `odom → base_link` | - | 里程计 TF |

## 文件清单

```
src/vehicle_bringup/
├── vehicle_bringup/
│   ├── __init__.py
│   └── chassis_node.py          # 底盘控制 ROS2 节点
├── launch/
│   └── bringup.launch.py        # 一键启动全系统
├── package.xml
├── setup.py
└── setup.cfg
```

## 开发进度

| 日期 | 完成内容 |
|------|----------|
| 第1周 | 搭建仓库、接口规范、包骨架 |
| 第2周 | 封装 ROS2 节点、发布 /odom、配置 TF |
| 第3周 | Nav2 完整链路联调 |
| 第4周 | 全系统联调、验证场景测试 |
