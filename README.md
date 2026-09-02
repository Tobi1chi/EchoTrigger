# Event-Triggered Audio Replay Agent

> An event-triggered replay stack for replaceable audio nodes, connected by a stable uplink contract to PC-side buffering and ASR.

中文说明见：[README.zh-CN.md](README.zh-CN.md)

![Node Contract](https://img.shields.io/static/v1?label=Node&message=Audio%20Uplink%20Contract&color=1f6feb)
![Firmware](https://img.shields.io/static/v1?label=Firmware&message=ESP-IDF&color=222222)
![ASR](https://img.shields.io/static/v1?label=ASR&message=Bailian%20Qwen%20ASR&color=0a7f5a)
![Audio](https://img.shields.io/static/v1?label=Audio&message=UDP%20PCM&color=b06d00)
![Control](https://img.shields.io/static/v1?label=Control&message=MQTT&color=8a3ffc)

## Architecture

### Overall

```mermaid
flowchart LR
  node["Audio Uplink Node<br/>any hardware implementing the contract"] -->|"UDP PCM<br/>node_uuid / node_id / sample metadata"| hub["PC Audio Hub"]
  mqtt["Control Plane<br/>MQTT-compatible topics"] <-->|"status / commands"| node
  hub --> ring["Rolling Buffer"]
  ring --> jobs["Async STT Jobs"]
  jobs --> asr["ASR Worker<br/>Bailian Qwen ASR by default"]
  mcp["MCP Client"] --> hub
```

This diagram shows the system contract: the software side expects an upstream node that can send protocol-compatible audio packets and expose a basic status/control plane. It does not require that node to be an `ESP32-S3`.

### Reference Hardware Architecture

```mermaid
flowchart LR
  mic["I2S Microphone<br/>INMP441"] --> capture["Capture<br/>16 kHz / 16-bit / mono"]
  capture --> packetizer["Packetizer<br/>20 ms PCM frames"]
  identity["ESP32-S3 STA MAC"] --> uuid["node_uuid"]
  uuid --> packetizer
  packetizer --> udp["UDP Uplink<br/>contract packet format"]
  cfg["Runtime Config<br/>Wi-Fi / MQTT / UDP / node_id"] --> udp
  cfg --> mqtt_hw["MQTT Telemetry and Control"]
  setup["AP/STA Setup Page"] --> cfg
```

The [Hardware/Mic-ESP32](Hardware/Mic-ESP32) firmware is one reference implementation of that contract, not the only hardware assumption of the PC hub.

## What This Repo Contains

- [Hardware/Mic-ESP32](Hardware/Mic-ESP32)
  reference `ESP32-S3` firmware for a microphone node.
- [Software/pc_hub](Software/pc_hub)
  PC-side UDP ingest, rolling buffer, MCP server, and cloud-first ASR worker.

Today the system does this:

- ingests audio nodes through a stable UDP PCM contract
- captures `16 kHz / 16-bit / mono PCM` on `ESP32-S3` in the reference firmware
- tracks nodes by `node_uuid`
- buffers recent audio on the PC
- submits async STT jobs to Alibaba Cloud Model Studio `qwen3-asr-flash` by default
- exposes MCP as the preferred AI-facing interface

## Fastest Path

### Hardware

Use the supported ESP-IDF 5.5.3 commands in:

- [Hardware/Mic-ESP32/README.md](Hardware/Mic-ESP32/README.md)

If the node has no runtime config, it boots into setup mode:

- connect to `MicSetup-<last6>`
- open `http://192.168.4.1/`
- fill Wi-Fi, MQTT, UDP, and `node_id`

### Software

The recommended runtime path is:

1. install the Python package
2. start `worker.main`
3. start `mcp_adapter.main`
4. use MCP as the primary interface

Minimal example:

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

MCP endpoint:

```text
http://127.0.0.1:8767/mcp
```

Legacy HTTP remains available for compatibility and debugging, but it is optional and disabled by default.

## Where To Read Next

- [Hardware/Mic-ESP32/README.md](Hardware/Mic-ESP32/README.md)
  Firmware setup, provisioning flow, build, flash, and node behavior.
- [Software/pc_hub/README.md](Software/pc_hub/README.md)
  Runtime model, configuration, recommended startup path, Docker, and legacy API.
- [docs/verification.md](docs/verification.md)
  Worker smoke checks, MCP validation notes, simulated uplink status, and legacy HTTP verification.
- [docs/protocols.md](docs/protocols.md)
  Audio uplink format, MQTT topics, timebase, and public integration contracts.

## Notes

- `node_uuid` is the stable backend key; the current reference firmware derives it from the ESP32-S3 STA MAC.
- `node_id` is the human-readable label configured locally.
- Query windows use `pc_receive_time`, not the embedded packet timestamp.
- The project is audio-first right now; video ingestion is future work.

## Star History

<a href="https://www.star-history.com/?repos=Tobi1chi%2FEchoTrigger&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=Tobi1chi/EchoTrigger&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=Tobi1chi/EchoTrigger&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=Tobi1chi/EchoTrigger&type=date&legend=top-left" />
 </picture>
</a>
