# YK_CANSDK_CPP

YK_CANSDK 的 C++17 移植版（Windows 10/11，Winsock2）。功能与
`../YK_CANSDK`（Python 金参考实现）完全对应：

- USR-CAN115 “标准协议转换”13 字节帧，扩展数据帧，TCP 拆包/粘包重同步；
- ID 1 前轴、ID 2 后轴，每台 M1 左轮、M2 右轮，默认 M2 反向；
- 前进/后退/缓转/原地旋转/四轮独立命令、斜坡、250 ms 上层看门狗；
- 上电每台 10 条零速解锁、`±300` 默认开环边界、故障字非零自动锁存急停；
- 解析速度、电气量、温度、故障、位置、参数应答；
- 参数写入构造器（拒绝 `0x0026`/`0x0027`）；
- 零第三方运行时依赖（仅标准库 + Winsock2）。

Python 原文件保留不动。协议字节、大端字节序、帧信息字节、ID 前缀 `0x0DEE`、
功能码表均与 Python 版逐字节一致。

> 这是会让真实车辆运动的代码。首次运行必须架空四轮、准备能够切断动力的
> 硬件急停，并由一人观察车辆、一人操作。软件急停、TCP 断线后的 500 ms
> 驱动器超时都不能替代硬件急停。

## 目录结构

```text
YK_CANSDK_CPP/
├─ include/ykcan/      头文件库（全 inline，无 .cpp 链接要求）
│  ├─ json.hpp         最小 JSON 解析/序列化
│  ├─ net.hpp          Winsock/BSD 跨平台 TCP Socket（超时连接、收发）
│  ├─ protocol.hpp     CanFrame、CanStreamParser、反馈类型、decode_feedback
│  ├─ config.hpp       NetworkConfig / SafetyLimits / VehicleConfig（JSON 加载）
│  ├─ client.hpp       GatewayClient（接收线程、回调、遥测缓存）
│  └─ vehicle.hpp      FourWheelVehicle（控制线程、斜坡、看门狗、急停）
├─ src/main.cpp        CLI：status / move（对应 python -m yk_can_sdk）
├─ examples/           decode_hex / monitor_feedback / basic_moves
├─ selftest.cpp        离线自检（与 Python tests/ 同向量）
├─ config.example.json 与 Python 版相同
├─ CMakeLists.txt
└─ build.ps1
```

与 Python 模块对照：`config.py→config.hpp`，`protocol.py→protocol.hpp`，
`client.py→client.hpp(+net.hpp)`，`vehicle.py→vehicle.hpp`，
`__main__.py→src/main.cpp`，`tests/*→examples/selftest.cpp`。

## 构建

本机当前未安装 C++ 工具链；安装任一工具后：

### 方式一：CMake（推荐）

```powershell
cmake -S . -B build
cmake --build build --config Release
.\build.ps1 -RunTests     # 或直接运行构建出的 ykcan_selftest.exe
```

### 方式二：MinGW / MSYS2（UCRT64）

```powershell
g++ -std=c++17 -Wall -Wextra -Iinclude src/main.cpp -lws2_32 -o ykcan_ctl
g++ -std=c++17 -Wall -Wextra -Iinclude examples/selftest.cpp -o ykcan_selftest
```

### 方式三：MSVC（Visual Studio Developer Prompt）

```powershell
cl /std:c++17 /W4 /Iinclude src\main.cpp /link ws2_32.lib
cl /std:c++17 /W4 /Iinclude examples\selftest.cpp /link ws2_32.lib
```

## 离线自检（先做这个）

`ykcan_selftest.exe` 不联网、不动车，逐字节验证 Python 金参考测试向量：

- `build_motor_frame(1, 100, -100)` → `88 0D EE 01 00 00 00 00 64 FF FF FF 9C`
- `build_motor_frame(2, -200, 200)` → `88 0D EE 02 00 FF FF FF 38 00 00 00 C8`
- 参数写入 `0x0028=2` → `88 0D EE 01 0A 83 00 28 00 00 02 00 00`，`0x26/0x27` 拒绝
- 粘包/拆包/杂字节重同步（丢弃 5 字节）、速度/电气/温度故障/参数应答解码
- 配置默认值、边界校验、JSON 往返

从项目根目录运行（需要同目录的 `config.example.json`）。

## 命令行

```powershell
.\build\Release\ykcan_ctl.exe --host 192.168.0.7 --port 5578 status --seconds 5
.\build\Release\ykcan_ctl.exe move --linear 0.10 --angular 0 --duration 0.5 --arm
```

`move` 必须带 `--arm`，与 Python 版行为一致。

## 与 Python 金参考的差异（有意为之）

| 项目 | Python | C++ |
|---|---|---|
| 回调注销 | 按函数对象相等移除 | 按 `add_feedback_callback` 返回的 token 移除 |
| `round()` | 银行家舍入 | `std::llround` 四舍五入（仅影响 .5 边界，实测命令多为整数） |
| 遥测返回 | 深拷贝对象 | `std::optional<DriverTelemetry>` 值拷贝快照 |

协议层（帧字节、解码结果、解析器丢弃计数）保证与 Python 完全一致。

## 使用前的 CAN115 配置

与 Python 版 README 相同：IP `192.168.0.7`、TCP Server、本地端口 `5578`、
CAN 250K、标准协议转换、双向、心跳/注册包关闭。详见
`../YK_CANSDK/README.md` 的“使用前的 CAN115 配置”一节。
