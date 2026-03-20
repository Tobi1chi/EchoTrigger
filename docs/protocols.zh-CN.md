# 协议与接入说明

## 设备身份

- `node_uuid`
  从 ESP32-S3 的 STA MAC 派生，是稳定的后端与 MQTT 主键
- `node_id`
  本地配置的人类可读名称

MQTT topics 使用 `mic/<node_uuid>/...`，不是 `mic/<node_id>/...`。

## 音频上行格式

- 采样率：`16000`
- 采样宽度：`16-bit`
- 声道：`1`
- 包时长：`20 ms`
- 传输方式：`UDP`

数据包格式定义在 `Hardware/Mic-ESP32/main/audio_protocol.h`，包含：

- `node_uuid`
- `node_id`
- 序列号
- 时间戳
- 采样元信息
- PCM payload

## MQTT Topics

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

### 控制命令

- `mic/<node_uuid>/cmd/streaming/set`
- `mic/<node_uuid>/cmd/restart`
- `mic/<node_uuid>/cmd/udp_target/set`

## 时间基准

Hub 的所有查询都使用 `pc_receive_time`。

查询时间轴不是设备包头里的嵌入式时间戳。

## Legacy HTTP API

legacy HTTP API 已废弃，而且默认关闭；启用后会暴露：

- `GET /nodes`
- `POST /query/audio`
- `POST /query/stt`
- `GET /jobs/<job_id>`

当前 `Qwen3-ASR` 成功任务可能返回：

- 任务状态
- clip 路径
- ASR 文本
- 为空的 `segments`
