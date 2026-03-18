# Mic-ESP32

> 面向 Event-Triggered Audio Replay Agent 的 `ESP32-S3` 麦克风节点固件。

English version: [README.md](README.md)

## 这个节点做什么

这份固件会把 `ESP32-S3` 变成一个轻量的音频上行节点：

- 从 `INMP441` 采集 `I2S` 音频
- 将音频按 `16 kHz / 16-bit / mono PCM` 分帧
- 通过 UDP 把音频发送到 PC Hub
- 通过 MQTT 暴露遥测和控制能力
- 使用 `NVS` 保存少量运行配置
- 在 `AP` 模式下提供首次网页配置门户

## 🔧 固件流程

```mermaid
flowchart LR
  mic["INMP441"] --> cap["audio_capture"]
  cap --> pkt["audio_packetizer"]
  pkt --> udp["udp_streamer"]
  cfg["device_config"] --> udp
  cfg --> mqtt["mqtt_control"]
  mon["health_monitor"] --> mqtt
```

## 当前 MVP 功能

| 区域 | 状态 |
| --- | --- |
| I2S 采集 | 已实现 |
| UDP 音频上行 | 已实现 |
| MQTT 控制命令（`streaming`、`restart`、`udp_target`） | 已实现 |
| MQTT 遥测与健康快照 | 已实现 |
| NVS 配置持久化 | 已实现 |
| 首次 AP 初始化门户 | 已实现 |
| `STA` 模式下的局域网重配置页面 | 已实现 |
| 配合 YOLO 视觉链路的视频上行 | 未实现 |

## 代码结构

| 路径 | 用途 |
| --- | --- |
| `main/main.c` | 启动、Wi‑Fi、任务编排 |
| `main/audio_capture.*` | I2S 采集与队列投递 |
| `main/audio_packetizer.*` | 包头与 PCM 分帧 |
| `main/udp_streamer.*` | UDP Socket 发送 |
| `main/mqtt_control.*` | MQTT 命令处理与遥测 |
| `main/device_config.*` | 默认配置与 NVS 持久化管理 |
| `main/health_monitor.*` | 运行计数器与状态快照 |
| `main/setup_portal.*` | AP/STA 配置门户与状态页 |

## 配置模式

这份固件目前支持两种部署路径。

### 1. 普通用户路径

- 烧录预编译固件
- 设备上电
- 如果节点尚未配置，会自动启动用于初始化的 Wi‑Fi AP
- 打开 `http://192.168.4.1/`
- 填写 Wi‑Fi、MQTT、UDP 和 `node_id`
- 保存并重启

节点连入正常 Wi‑Fi 后，还会在 `STA` 模式下继续提供一个轻量配置页，方便后续重新配置。

### 2. 开发者路径

- 可选通过 `device_secrets.h` 提供编译期默认值
- 使用 `ESP-IDF` 构建
- 本地烧录和调试

如果没有提供编译期 secrets，固件仍然可以启动，并自动回退到 setup portal。

## 构建前准备

### 1. 创建 secrets 文件

创建：

- [`main/device_secrets.h`](main/device_secrets.h)

参考：

- [`main/device_secrets.h.example`](main/device_secrets.h.example)

需要填写：

- `DEVICE_SECRET_WIFI_SSID`
- `DEVICE_SECRET_WIFI_PASS`
- `DEVICE_SECRET_MQTT_HOST`
- `DEVICE_SECRET_MQTT_PORT`
- `DEVICE_SECRET_MQTT_USER`
- `DEVICE_SECRET_MQTT_PASS`
- `DEVICE_SECRET_UDP_HOST`
- `DEVICE_SECRET_UDP_PORT`
- `DEVICE_SECRET_NODE_ID`

这个文件是可选的。如果不存在，固件会使用内置的空默认值，并等待通过 setup portal 完成初始化。

### 2. 检查设备默认值

检查 [`main/device_config.c`](main/device_config.c) 中这些默认项是否符合你的硬件：

- I2S GPIO 引脚映射
- 用于强制重新配网的 setup 按键引脚
- `streaming_enabled`
- `telemetry_interval_ms`

Wi‑Fi、MQTT、UDP 和 `node_id` 的默认值来自 `device_secrets.h`，也可以通过配置门户填写。

### 3. 检查接线

确认开发板和麦克风接线与配置中的引脚一致。

## 设备身份模型

固件采用两层身份设计：

- `node_uuid`
  - 自动从 ESP32-S3 的 STA MAC 派生
  - 格式为 `esp32s3-<12 hex mac>`
  - 用作稳定的后端 / MQTT 主键
- `node_id`
  - 人类可读名称
  - 可以单独改名

## 首次初始化门户

当设备还没有有效运行配置时，它会启动：

- 名为 `MicSetup-<last6>` 的 Wi‑Fi 热点
- 一个位于 `http://192.168.4.1/` 的轻量配置页

热点密码是：

```text
mic-setup
```

配置页允许用户填写：

- Wi‑Fi SSID 和密码
- MQTT host、port、username、password
- UDP host 和 port
- `node_id`

保存后，设备会把这些值写入 `NVS`，然后重启进入正常 `STA` 模式。

## 局域网重配置页面

当节点已经配置完成并连接到路由器后，它会在本地局域网 IP 上继续提供相同的配置表单。

也就是说，你可以：

- 在路由器或 DHCP 租约里找到节点 IP
- 打开 `http://<device-ip>/`
- 修改 Wi‑Fi、MQTT、UDP 或 `node_id`
- 保存并重启

当前限制：

- 暂时没有 `mDNS` 主机名
- 暂时没有额外认证机制，只依赖局域网访问边界

## 强制恢复配置模式

如果设备已经保存过配置，但你仍然需要强制它重新进入 AP 配网模式，可以在启动时将独立的 setup 按键持续拉低 5 秒。

硬件说明：

- 默认恢复输入在 [`main/device_config.c`](main/device_config.c) 中映射到 `GPIO9`
- 不要在 ESP32-S3 板子上把这条恢复路径接到 `GPIO0`，因为 `GPIO0` 是 strapping pin，而且通常与板载 BOOT 按键相连
- 如果你的硬件把 setup 按键接到了其他非 strapping GPIO，请在 [`main/device_config.c`](main/device_config.c) 中修改 `setup_button_pin`

## 构建

```sh
bash -lc '
export IDF_PATH=$HOME/.espressif/v5.5.3/esp-idf
export IDF_TOOLS_PATH=$HOME/.espressif/tools
export IDF_PYTHON_ENV_PATH=$HOME/.espressif/tools/python/v5.5.3/venv
export ESP_ROM_ELF_DIR=$HOME/.espressif/tools/esp-rom-elfs/20241011
export PATH=$HOME/.espressif/tools/python/v5.5.3/venv/bin:$HOME/.espressif/tools/cmake/3.30.2/CMake.app/Contents/bin:$HOME/.espressif/tools/ninja/1.12.1:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/xtensa-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/riscv32-esp-elf/bin:$PATH
cd /Users/tobiichieigetsu/Workspace/AI/Microphone/Hardware/Mic-ESP32
$HOME/.espressif/tools/python/v5.5.3/venv/bin/python $IDF_PATH/tools/idf.py build
'
```

## 烧录

```sh
bash -lc '
export IDF_PATH=$HOME/.espressif/v5.5.3/esp-idf
export IDF_TOOLS_PATH=$HOME/.espressif/tools
export IDF_PYTHON_ENV_PATH=$HOME/.espressif/tools/python/v5.5.3/venv
export ESP_ROM_ELF_DIR=$HOME/.espressif/tools/esp-rom-elfs/20241011
export PATH=$HOME/.espressif/tools/python/v5.5.3/venv/bin:$HOME/.espressif/tools/cmake/3.30.2/CMake.app/Contents/bin:$HOME/.espressif/tools/ninja/1.12.1:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/xtensa-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/riscv32-esp-elf/bin:$PATH
cd /Users/tobiichieigetsu/Workspace/AI/Microphone/Hardware/Mic-ESP32
$HOME/.espressif/tools/python/v5.5.3/venv/bin/python $IDF_PATH/tools/idf.py -p <SERIAL_PORT> flash monitor
'
```

## 音频上行格式

- 采样率：`16000`
- 采样宽度：`16-bit`
- 声道：`1`
- 包时长：`20 ms`
- 传输方式：`UDP`

数据包格式定义在 [`main/audio_protocol.h`](main/audio_protocol.h)，包含：

- `node_uuid`
- `node_id`
- 序列号
- 时间戳
- 采样元信息
- PCM payload

## 📡 MQTT Topics

### 状态上报

- `mic/<node_uuid>/status/availability`
- `mic/<node_uuid>/status/node_id`
- `mic/<node_uuid>/status/node_uuid`
- `mic/<node_uuid>/status/streaming`
- `mic/<node_uuid>/status/rssi`
- `mic/<node_uuid>/status/uptime`
- `mic/<node_uuid>/status/packets_sent`
- `mic/<node_uuid>/status/packets_dropped`
- `mic/<node_uuid>/status/udp_target`

`STA` 模式下的本地配置页还会显示一份实时状态快照，包括：

- 当前 IP 地址
- Wi‑Fi 状态和 RSSI
- MQTT 连接状态
- UDP 就绪状态
- 运行时长
- 已发送 / 已丢弃的数据包数量

### 控制命令

- `mic/<node_uuid>/cmd/streaming/set`
- `mic/<node_uuid>/cmd/restart`
- `mic/<node_uuid>/cmd/udp_target/set`

## 备注

- 音频走 UDP，不走 MQTT
- 节点设计上就是纯音频上行，不以本地长期音频归档为目标
- PC Hub 负责滚动缓存保留
- `node_uuid` 会在每次启动时由 STA MAC 派生，因此重刷固件后仍保持稳定
- 缺少 Wi‑Fi / MQTT / UDP 配置的节点会自动进入 setup portal 模式
