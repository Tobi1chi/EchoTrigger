# 事件触发音频回放代理

> 一个面向可替换音频节点的事件触发回放系统：通过稳定上行契约连接边缘采集、PC 侧缓存和 ASR。

English version: [README.md](README.md)

![Node Contract](https://img.shields.io/static/v1?label=Node&message=Audio%20Uplink%20Contract&color=1f6feb)
![Firmware](https://img.shields.io/static/v1?label=Firmware&message=ESP-IDF&color=222222)
![ASR](https://img.shields.io/static/v1?label=ASR&message=Bailian%20Qwen%20ASR&color=0a7f5a)
![Audio](https://img.shields.io/static/v1?label=Audio&message=UDP%20PCM&color=b06d00)
![Control](https://img.shields.io/static/v1?label=Control&message=MQTT&color=8a3ffc)

## 架构

### 整体架构

```mermaid
flowchart LR
  node["音频上行节点<br/>任意满足契约的硬件"] -->|"UDP PCM<br/>node_uuid / node_id / sample metadata"| hub["PC Audio Hub"]
  mqtt["控制面<br/>MQTT-compatible topics"] <-->|"状态 / 命令"| node
  hub --> ring["滚动缓存"]
  ring --> jobs["异步 STT 任务"]
  jobs --> asr["ASR Worker<br/>默认百炼 Qwen ASR"]
  mcp["MCP 客户端"] --> hub
```

这张图表达系统契约：软件侧只要求上游节点能按协议发送音频包并暴露基础状态/控制面，不要求节点一定是 `ESP32-S3`。

### 参考硬件架构

```mermaid
flowchart LR
  mic["I2S 麦克风<br/>INMP441"] --> capture["采集<br/>16 kHz / 16-bit / mono"]
  capture --> packetizer["分包<br/>20 ms PCM frames"]
  identity["ESP32-S3 STA MAC"] --> uuid["node_uuid"]
  uuid --> packetizer
  packetizer --> udp["UDP 上行<br/>契约包格式"]
  cfg["运行配置<br/>Wi-Fi / MQTT / UDP / node_id"] --> udp
  cfg --> mqtt_hw["MQTT 遥测与控制"]
  setup["AP/STA 配置页面"] --> cfg
```

当前仓库里的 [Hardware/Mic-ESP32](Hardware/Mic-ESP32) 是上述契约的一种参考实现，而不是 PC hub 的唯一硬件前提。

## 仓库包含什么

- [Hardware/Mic-ESP32](Hardware/Mic-ESP32)
  基于 `ESP32-S3` 的参考麦克风节点固件。
- [Software/pc_hub](Software/pc_hub)
  PC 侧 UDP 接收、滚动缓冲、MCP 服务和云端优先 ASR worker。

当前系统能力：

- 通过稳定的 UDP PCM 契约接入音频上行节点
- 参考固件在 `ESP32-S3` 上采集 `16 kHz / 16-bit / mono PCM`
- 通过 `node_uuid` 跟踪节点
- 在 PC 上缓存最近一段时间的音频
- 默认把 STT 任务异步提交给阿里云百炼 `qwen3-asr-flash`
- 默认通过 MCP 提供 AI 访问入口

## 最快跑通路径

### 硬件

请直接使用这里维护的 ESP-IDF 5.5.3 受支持命令：

- [Hardware/Mic-ESP32/README.zh-CN.md](Hardware/Mic-ESP32/README.zh-CN.md)

如果节点还没有运行配置，它会进入 setup 模式：

- 连接 `MicSetup-<last6>`
- 打开 `http://192.168.4.1/`
- 填写 Wi-Fi、MQTT、UDP 和 `node_id`

### 软件

推荐的软件启动路径是：

1. 安装 Python 包
2. 启动 `worker.main`
3. 启动 `mcp_adapter.main`
4. 通过 MCP 使用系统

最小示例：

```powershell
cd Software/pc_hub
uv sync

$env:DASHSCOPE_API_KEY="your-api-key"
$env:PC_HUB_ASR_PROVIDER="bailian"
$env:PC_HUB_ASR_LANGUAGE="zh"
uv run python -m worker.main
```

```powershell
cd Software/pc_hub
$env:PC_HUB_MCP_BIND_HOST="127.0.0.1"
$env:PC_HUB_MCP_PORT="8767"
$env:PC_HUB_MCP_PATH="/mcp"
uv run python -m mcp_adapter.main
```

MCP 端点：

```text
http://127.0.0.1:8767/mcp
```

legacy HTTP 仍然可用于兼容和手动调试，但它不是默认路径，而且默认关闭。

## 继续阅读

- [Hardware/Mic-ESP32/README.zh-CN.md](Hardware/Mic-ESP32/README.zh-CN.md)
  固件配网流程、构建、烧录和节点行为。
- [Software/pc_hub/README.zh-CN.md](Software/pc_hub/README.zh-CN.md)
  运行模型、配置项、推荐启动方式、Docker 和 legacy API。
- [docs/verification.zh-CN.md](docs/verification.zh-CN.md)
  worker 冒烟测试、MCP 验证说明、模拟上行验证和 legacy HTTP 验证。
- [docs/protocols.zh-CN.md](docs/protocols.zh-CN.md)
  音频上行格式、MQTT topics、时间基准和对外接口约定。

## 备注

- `node_uuid` 是稳定的后端主键；当前参考固件由 ESP32-S3 的 STA MAC 派生。
- `node_id` 是本地可改的人类可读名称。
- 查询使用 `pc_receive_time`，不是设备包头里的时间戳。
- 当前项目以音频为主，视频接入仍是后续工作。

## Star History

<a href="https://www.star-history.com/?repos=Tobi1chi%2FEchoTrigger&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=Tobi1chi/EchoTrigger&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=Tobi1chi/EchoTrigger&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=Tobi1chi/EchoTrigger&type=date&legend=top-left" />
 </picture>
</a>
