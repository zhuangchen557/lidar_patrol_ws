# YK CAN SDK 接口文档

本文档对应 `yk_can_sdk` 0.1.0。所有高级运动接口都使用“正值让车轮推动车体前进”的逻辑方向；协议层 `build_motor_frame()` 则使用驱动器原始方向。

## 配置类

### `NetworkConfig`

```python
NetworkConfig(
    host="192.168.0.7",
    port=5578,
    connect_timeout_s=5.0,
    receive_timeout_s=0.2,
)
```

- `host`：USR-CAN115 的 IP。
- `port`：CAN115 处于 TCP Server 模式时的“本地端口”。它是 Windows 程序连接的目标端口，不是 Windows 客户端自己的源端口。
- 两个 timeout 仅控制 Socket 连接和接收循环，不改变驱动器的 500 ms 通信超时。

### `SafetyLimits`

```python
SafetyLimits(
    max_command=300,
    command_period_s=0.02,
    command_watchdog_s=0.25,
    max_acceleration_per_s=600.0,
    max_deceleration_per_s=1200.0,
    max_continuous_motion_s=10.0,
    unlock_repetitions=10,
    stop_repetitions=10,
    auto_estop_on_fault=True,
)
```

- `max_command`：开环逻辑控制值硬边界，允许范围 `1..1100`，默认仅 `300`。
- `command_period_s`：两台驱动器控制刷新周期，默认 20 ms，强制不大于 100 ms。
- `command_watchdog_s`：上层未刷新目标时当前值和目标立即归零，强制小于驱动器 500 ms 超时。
- `max_acceleration_per_s` / `max_deceleration_per_s`：每秒允许变化的控制单位。
- `max_continuous_motion_s`：一次 `move_for()` 最长持续时间。
- `unlock_repetitions`：连接时每台发送零速的次数，最小为手册要求的 10 次。
- `auto_estop_on_fault`：收到功能码 `0x03` 且故障字非零时锁存急停。

### `VehicleConfig`

默认拓扑：驱动器 1 为前轴，驱动器 2 为后轴；每台 M1 为左轮、M2 为右轮；根据调试表记录，M2 的默认方向系数为 `-1`。

```python
config = VehicleConfig.from_json("config.example.json")
```

方向系数只能是 `+1` 或 `-1`。若现场逐轮架空测试结果不同，只改对应的 `*_sign`，不要在业务代码中到处取反。

## 高级车辆接口 `FourWheelVehicle`

### 生命周期

```python
with FourWheelVehicle(config) as car:
    ...
```

进入上下文会：连接 CAN115、给 ID1 和 ID2 各发至少 10 条零速、启动接收线程和 50 Hz 控制线程。退出时立即把目标与当前值归零、重复发送零速，再关闭 Socket。

也可以显式调用：

- `connect()`：连接、零速解锁、启动控制循环。
- `close()`：零速连发并关闭；可重复调用。
- `is_connected`：TCP 接收线程认为连接是否有效。

### 连续控制

```python
car.set_motion(linear=0.2, angular=0.0)
```

- `linear`、`angular` 均在 `[-1.0, 1.0]`。
- 正 `linear` 前进，负值后退；正 `angular` 左转，负值右转。
- 差速混合为 `left = linear - angular`、`right = linear + angular`，超出单位圆时按比例归一，不会超过 `max_command`。
- 调用只更新目标。控制线程负责斜坡和周期发送；上层必须在 `command_watchdog_s` 内再次调用，否则目标自动归零。

```python
car.set_wheel_commands(left=100, right=150)
car.set_axle_commands(front_left=100, front_right=150, rear_left=95, rear_right=145)
```

- `set_wheel_commands()`：前后轴使用相同左右轮命令。
- `set_axle_commands()`：四轮独立逻辑命令，适合后续做轴间校准。
- 任一值超过 `±max_command`、为 NaN 或无穷大时立即抛出 `ValueError`，不会静默截断。

### 有时长的动作

```python
car.move_for(linear=0.15, angular=0.0, duration_s=1.0)
car.forward(speed=0.15, duration_s=1.0)
car.backward(speed=0.15, duration_s=1.0)
car.turn_left(speed=0.15, turn=0.08, duration_s=1.0)
car.turn_right(speed=0.15, turn=0.08, duration_s=1.0)
car.spin_left(speed=0.12, duration_s=0.5)
car.spin_right(speed=0.12, duration_s=0.5)
```

这些都是阻塞接口，会主动刷新软件看门狗，并在正常结束时停车。`duration_s` 必须不大于 `max_continuous_motion_s`。发生异常或 `KeyboardInterrupt` 时会锁存急停。

### 停车和急停

- `stop()`：立即发一组零速，但不锁存，后续可继续调用运动接口。
- `smooth_stop(timeout_s=1.0)`：按减速度下降，超时后强制立即停车。
- `emergency_stop(reason="...")`：目标和当前值立即归零、零速连发并锁存；锁存期间所有新运动命令都被拒绝。
- `clear_emergency_stop()`：确认当前缓存中没有活动故障后，重新发送 10 组零速并解除锁存。
- `estop_latched` / `estop_reason`：查看急停状态与原因。

软件急停不能代替切断动力回路的硬件急停。

### 高层反馈

- `get_logical_wheel_speeds()`：若两台都已有速度反馈，返回 `WheelCommands`，并按配置方向转换成车体逻辑方向；否则返回 `None`。
- `get_logical_wheel_positions()`：同上，内容为位置/霍尔计数。
- `current_commands`：控制循环最近实际发送的四轮逻辑值。

## 网络客户端 `GatewayClient`

适合不需要底盘混控、只做协议开发的场景。

```python
with GatewayClient(NetworkConfig()) as client:
    client.send_motor_raw(1, 100, -100)
    state = client.wait_for_feedback(1, timeout_s=1.0)
```

- `send_frame(frame)`：发送任意合法 `CanFrame`。
- `send_motor_raw(driver_id, motor1, motor2)`：发送功能码 `0x00`；不会应用车辆方向映射或开环 `±1100` 边界。
- `add_feedback_callback(callback)` / `remove_feedback_callback(callback)`：回调运行在接收线程，必须快速返回；回调异常会被隔离。
- `get_telemetry(driver_id)`：返回线程安全的深拷贝 `DriverTelemetry`。
- `wait_for_feedback(driver_id, timeout_s)`：等待该 ID 任一反馈进入缓存。
- `last_error`：网络线程最后一次异常。
- `parser.discarded_bytes`：为重建 13 字节边界而丢弃的杂字节数量；持续增长通常说明 CAN115 注册包/心跳包未关闭或转换模式不对。

`DriverTelemetry` 分别缓存最近的 `speed`、`electrical`、`thermal_fault`、`position`、`parameter_ack`。

## 协议接口

### 构造帧

```python
frame = build_motor_frame(driver_id=1, motor1=100, motor2=-100)
packet = frame.to_gateway_bytes()
# 88 0D EE 01 00 00 00 00 64 FF FF FF 9C
```

`build_parameter_write_frame(driver_id, register, value)` 构造 V1.221+ 参数写入。SDK 无条件拒绝说明书标注“勿动”的 `0x0026`、`0x0027`。参数写入不会自动执行，调用方仍要逐台隔离、备份原值并自行发送。

### 流式解析

```python
parser = CanStreamParser()
for frame in parser.feed(sock_bytes):
    feedback = decode_feedback(frame)
```

解析器处理 TCP 拆包、粘包，并通过帧信息、`0x0DEE` 前缀、ID 和功能码重建边界。

### 返回类型

- `SpeedFeedback`：`motor1`、`motor2`，有符号 int32；非位置模式通常为速度。
- `ElectricalFeedback`：两路电流和电源电压，按手册除以 10；末尾两字节保留为 `tail`，兼容固件中的通道字段差异。
- `ThermalFaultFeedback`：两侧温度除以 10，两路 16 位故障字解析为 `Fault`。
- `PositionFeedback`：两路有符号 int32 位置/霍尔计数。
- `ParameterAck`：命令、寄存器、设置值和保留字节。
- `RawFeedback`：已通过 YK 帧验证但 SDK 未专门解释的功能码。

## 故障位 `Fault`

| 位 | 枚举 | 含义 |
|---:|---|---|
| 0 | `OVERCURRENT` | 电流过大 |
| 1 | `LOAD_ABNORMAL` | 负载异常 |
| 2 | `OVERTEMPERATURE` | 温度过高保护 |
| 3 | `OVERVOLTAGE` | 电压过高 |
| 4 | `UNDERVOLTAGE` | 电压过低 |
| 5 | `STALL` | 堵转保护 |
| 6 | `HALL_ABNORMAL` | 霍尔信号异常 |
| 7 | `ABNORMAL_JITTER` | 异常抖动 |

`fault.labels_zh` 可直接得到所有活动故障的中文元组。
