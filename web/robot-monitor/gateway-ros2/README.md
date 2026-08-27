# gateway-ros2（rosbridge 版实验台网关）

解决「雷达 USB 挂到 WSL 后 EnzoPatrolLab 直读 COM 口失效」问题的网关实现：
雷达数据通过 **rosbridge**（ws://127.0.0.1:9090）从 WSL 侧 `/scan` 获取，温湿度仍由 Windows 串口直读。

## 与旧版 gateway 的差异

| 能力 | 旧版 gateway（1.0.0） | gateway-ros2 |
|------|------------------------|--------------|
| 雷达数据源 | 无（仅 rosbridge 传感器） | **rosbridge `/scan`**（WSL → LD19 驱动） |
| 温湿度 | rosbridge `/sensor/*` 话题 | **Windows COM 口直读**（LES11B Modbus RTU） |
| 底盘探测 | 无 | TCP 探测 `192.168.0.7:5578` |
| 前端兼容 | 旧前端 | **EnzoPatrolLab 0.2.0 前端**（完整 robot_status 结构） |

## 数据链路

```
雷达 USB → WSL (ldlidar → /scan BEST_EFFORT)
  → scan_repub 节点（双 QoS 转发 → /scan RELIABLE）
  → rosbridge_server (ws://127.0.0.1:9090)
  → gateway-ros2 订阅 /scan → [[x, y, intensity], ...]
  → WebSocket /ws/robot → EnzoPatrolLab 前端雷达图

温湿度 COM3 → gateway-ros2 (Modbus RTU) → /ws/robot → 前端仪表盘
```

## 部署（EnzoPatrolLab 包内）

1. 拷贝本目录 `app/` 到 `EnzoPatrolLab-*/resources/app/gateway/app/`
2. 在 `resources/app/gateway/` 创建标记文件 `USE_SOURCE.flag`
3. 修改 `resources/app/desktop/main.cjs` 的 `startGateway()`：
   检测到 `USE_SOURCE.flag` 时用源码模式启动（`python -m uvicorn app.main:app --port 8000`），否则回退 exe
4. 安装依赖：`pip install fastapi "uvicorn[standard]" pyserial websocket-client`
5. `experiment-config.json` 中 `usbSensor.port` 设为温湿度实际 COM 口（如 `COM3`）

## 启动前置条件

- WSL 内运行：LD19 驱动（/scan）、scan_repub（双 QoS 转发）、rosbridge_server（sagac1ty 用户）
  > 注意：rosbridge 必须与 LD19 同用户（root 下 DDS 跨用户发现失败）
- Windows 侧：EnzoPatrolLab 自动拉起 gateway（源码模式）

## 环境变量（与 0.2.0 main.cjs 对齐）

`GATEWAY_HOST / GATEWAY_PORT / FRONTEND_ORIGINS / ROSBRIDGE_URL / USB_SENSOR_PORT /
USB_SENSOR_AUTO_DETECT / USB_SENSOR_BAUDRATE / USB_SENSOR_SLAVE_ID / CHASSIS_PROBE_ENABLED /
CHASSIS_HOST / CHASSIS_PORT / LIDAR_* / HISTORY_DB`
