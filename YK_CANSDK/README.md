# YK_CANSDK

面向 Windows 的纯 Python 小车 SDK。它通过 TCP 连接 USR-CAN115，再用南京运康自定义扩展 CAN 帧控制两台双路电机驱动器：驱动器 ID 1 控制前轮，ID 2 控制后轮。SDK 提供四轮差速运动、边界保护、零速解锁、周期保活、故障自动急停、TCP 流重组和 CAN 返回解析。

默认连接参数已经按当前设备设置为 `192.168.0.7:5578`。

> 这是会让真实车辆运动的代码。首次运行必须架空四轮、准备能够切断动力的硬件急停，并由一人观察车辆、一人操作。软件急停、TCP 断线后的 500 ms 驱动器超时都不能替代硬件急停。

## 已实现范围

- USR-CAN115 “标准协议转换”13 字节格式，扩展数据帧和 TCP 拆包/粘包重同步；
- ID 1 前轴、ID 2 后轴，每台 M1 左轮、M2 右轮；
- 根据调试表默认 M1 正向、M2 反向，并允许每轮独立配置；
- 前进、后退、缓转、原地旋转、四轮独立命令；
- 上电每台 10 条零速，默认 20 ms 控制刷新；
- `±300` 默认开环上限、斜坡、250 ms 上层看门狗、单动作最长 10 秒；
- 网络异常、回调故障、手动急停时归零；功能码 `0x03` 非零故障自动锁存急停；
- 解析速度、电流、电压、温度、故障、位置和参数设置应答；
- 参数写入构造器，并禁止说明书标注“勿动”的 `0x0026`、`0x0027`；
- 无第三方运行依赖，Python 3.10+，Windows 10/11 可运行。

本 SDK 不自动改写驱动器模式、ID、极对数、电流、电压或 CAN 波特率。此类参数与硬件相关，误写可能导致失控或返厂。

## 使用前的 CAN115 配置

用 USR-CAN115 配置软件读取并确认：

| 项目 | 值 |
|---|---|
| IP | `192.168.0.7`，Windows 网卡必须同网段 |
| Socket 模式 | TCP Server |
| 本地端口 | `5578` |
| CAN 波特率 | `250K`，与运康驱动器默认值一致 |
| CAN 工作模式 | 正常 |
| 转换模式 | 标准协议转换 |
| 转换方向 | 双向 |
| 过滤 | 首次排障可关闭；稳定后仅接收扩展帧 |
| 打包 | 调试建议 1 帧、1~10 ms；SDK 不依赖 TCP 包边界 |
| 网络/CAN 心跳 | 关闭 |
| 注册包 | 关闭 |

“本地端口 5578”指 CAN115 的 TCP Server 监听端口。Windows 程序是 TCP Client，连接目标为 `192.168.0.7:5578`；不应强行把 Windows 客户端自己的源端口也绑定成 5578。

## 接线和驱动器前提

1. CAN115 `H` 接两台驱动器 `CAN_H`，`L` 接 `CAN_L`，尽量使用线型总线。
2. 总线两个物理端点各保留一个 120 Ω。CAN115 位于端点时短接 `RS-L` 才会接入其内置 120 Ω；断电测 H-L 约为 60 Ω。
3. 两台驱动器 ID 必须分别为 1、2。若同为 1，只连接待修改的单台驱动器，写寄存器 `0x0028=2` 并重启确认，不能让两个同 ID 设备同时在线修改。
4. 驱动器 CAN 默认为 250K；CAN115 说明书中的默认值可能不同，必须显式核对。
5. 确认驱动器处于预期的开环/速度/位置模式。本项目的默认 `±300` 边界按开环 `±1100` 设计。
6. CAN 控制优先级高于 RS485、PWM、SBUS 和配置口。电脑持续发送 CAN 时，遥控器可能无法接管。

## Windows 安装

在 PowerShell 进入本目录：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -v
```

如果执行策略阻止激活脚本，也可以始终使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -v
```

SDK 本身只依赖 Python 标准库。

## 第一次安全联调

先不要运行运动示例。按以下顺序进行：

1. 架空四轮，确认硬件急停有效，周围无人和障碍物。
2. 复制 `config.example.json`，核对 IP、端口、两个 ID 和 `max_command=300`。
3. 只连接并保持零速，观察反馈：

```powershell
python -m yk_can_sdk --host 192.168.0.7 --port 5578 status --seconds 5
```

4. 若无反馈，检查 NET/CAN/WORK 指示灯、250K、H/L、终端电阻、标准协议和双向转换。不要用更大控制值“试出来”。
5. 逐轮测试方向。建议临时用高级接口把另三轮设为 0，每次从逻辑值 30~50 开始。确认左轮是 M1、右轮是 M2，以及正值确实推动车体前进；不符时仅修改 JSON 中对应 `*_sign`。
6. 方向确认后，才可运行一次 0.5 秒低值运动：

```powershell
python -m yk_can_sdk move --linear 0.10 --angular 0 --duration 0.5 --arm
```

CLI 故意要求 `--arm` 才会运动。

## Python 快速开始

```python
from yk_can_sdk import FourWheelVehicle, VehicleConfig

config = VehicleConfig.from_json("config.example.json")

with FourWheelVehicle(config) as car:
    car.forward(speed=0.15, duration_s=1.0)
    car.turn_left(speed=0.15, turn=0.08, duration_s=0.8)
    car.stop()

    front = car.client.get_telemetry(config.front_driver_id)
    rear = car.client.get_telemetry(config.rear_driver_id)
    print(front)
    print(rear)
```

上下文进入时连接、给两台各发 10 条零速并启动控制循环；离开时零速连发后断开。不要用裸 `socket.close()` 代替 `car.close()`。

连续遥控或自动驾驶应周期调用：

```python
car.set_motion(linear=0.2, angular=-0.1)
```

如果 250 ms 内没有刷新，SDK 自动把目标设为零。驱动器自身约 500 ms 无正确命令也会停机，形成第二层看门狗。

## 运动边界

| 边界 | 默认 | 行为 |
|---|---:|---|
| 开环轮命令 | `±300` | 超出直接抛异常，不截断 |
| 手册开环绝对极限 | `±1100` | 配置也不允许超过 |
| 线速度/角速度输入 | `[-1, 1]` | 差速混合后按比例归一 |
| 控制周期 | 20 ms | 配置强制 10~100 ms |
| 上层命令看门狗 | 250 ms | 未刷新时当前值和目标立即归零 |
| 驱动器通信超时 | 约 500 ms | 来自设备说明书 |
| 默认加速度 | 600 单位/s | 控制线程做斜坡 |
| 默认减速度 | 1200 单位/s | 看门狗停车更快 |
| 单次阻塞动作 | 最长 10 s | 超出抛异常 |
| 故障字非零 | 任意位 | 自动锁存急停 |

`max_command` 不是 m/s 或 rpm。由于资料没有提供轮径、减速比、额定转速和底盘轮距，SDK 不虚构物理单位。后续可根据实车标定在上层把 m/s、rad/s 转为这里的逻辑控制值。

## 返回解析

CAN115 可能把多帧合并到一次 TCP 接收，也可能拆开一帧。`CanStreamParser` 会维护缓存并按 13 字节固定格式重组，同时检查扩展帧标记、DLC、`0x0DEE` 前缀、驱动器地址和功能码。

| 功能码 | 解析类型 | 主要字段 |
|---:|---|---|
| `0x01` | `SpeedFeedback` | 两路 int32 速度/模式数据 |
| `0x02` | `ElectricalFeedback` | 两路电流、电源电压、原始尾字节 |
| `0x03` | `ThermalFaultFeedback` | 两侧温度、两路故障位 |
| `0x04` | `PositionFeedback` | 两路 int32 位置/霍尔计数 |
| `0x0B` | `ParameterAck` | 命令、寄存器、设置值 |

`get_logical_wheel_speeds()` 与 `get_logical_wheel_positions()` 会应用 JSON 中的方向系数；`GatewayClient` 缓存里的协议反馈保留驱动器原始符号，便于排查。

功能码 `0x02` 最后两字节在说明书不同表格中有“保留”与通道值两种表述，SDK 将其保留为 `tail`，不做未经验证的解释。

## 示例

- `examples/basic_moves.py`：有限时长的前后、缓转和原地转向。
- `examples/monitor_feedback.py`：持续零速并打印两台解析结果。
- `examples/keyboard_control.py`：Windows `msvcrt` 键盘示例，带命令看门狗。
- `examples/decode_hex.py`：完全离线解析一条十六进制返回帧。

运行示例：

```powershell
python examples\monitor_feedback.py
python examples\decode_hex.py
```

## 文件说明

```text
YK_CANSDK/
├─ yk_can_sdk/
│  ├─ config.py       网络、拓扑、方向和安全边界
│  ├─ protocol.py     13字节帧、指令构造、流解析、返回数据类型
│  ├─ client.py       TCP连接、接收线程、回调和状态缓存
│  ├─ vehicle.py      双驱动器四轮控制、斜坡、看门狗、急停
│  └─ __main__.py     安全默认的命令行入口
├─ docs/
│  ├─ API.md          完整接口说明
│  └─ PROTOCOL.md     协议字段、ID、返回格式和兼容策略
├─ examples/          运动、监控、键盘和离线解析案例
├─ tests/             协议向量、边界、方向和解析单元测试
├─ config.example.json
└─ pyproject.toml
```

详细接口见 [docs/API.md](docs/API.md)，协议推导见 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

## 测试与验证

```powershell
python -m compileall -q yk_can_sdk examples tests
python -m unittest discover -v
```

测试使用调试表中的已知报文向量，例如逻辑前进 100 对应原始 `M1=+100, M2=-100`：

```text
88 0D EE 01 00 00 00 00 64 FF FF FF 9C
```

离线测试不会连接 `192.168.0.7`，也不会让车辆运动。仓库交付前未主动连接真实车辆；现场方向、驱动模式、机械极限和故障反馈必须按“第一次安全联调”验证。

## 已知限制和后续扩展点

- 说明书一处称“CANOPEN”，但后续定义的是 `0x0DEE...` 自定义扩展帧；实现采用具体帧表和工作簿实测向量，不实现 CANopen 对象字典。
- 未知轮径、轮距、减速比和额定转速，因此没有 m/s 或里程计融合。
- TCP 断开后不自动重连。自动重连可能在恢复网络时意外重新运动，建议由上层状态机在人工确认后重新 `connect()`。
- 位置闭环和速度闭环的安全值依赖电机参数，本版只提供协议原语，不提供未经标定的车辆动作封装。
- 软件无法判断硬件急停、障碍物、人员、地面附着和机械碰撞；正式无人运行需另加独立安全控制器、障碍检测和动力切断回路。
