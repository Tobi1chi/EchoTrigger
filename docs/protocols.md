# Protocols And Integration Notes

## Device Identity

- `node_uuid`
  derived from the ESP32-S3 STA MAC and used as the stable backend and MQTT key
- `node_id`
  human-readable label configured locally

MQTT topics use `mic/<node_uuid>/...`, not `mic/<node_id>/...`.

## Audio Uplink Format

- sample rate: `16000`
- sample width: `16-bit`
- channels: `1`
- packet duration: `20 ms`
- transport: `UDP`

The packet format is defined in `Hardware/Mic-ESP32/main/audio_protocol.h` and includes:

- `node_uuid`
- `node_id`
- sequence number
- timestamp
- sample metadata
- PCM payload

## MQTT Topics

### Status

- `mic/<node_uuid>/status/availability`
- `mic/<node_uuid>/status/node_id`
- `mic/<node_uuid>/status/node_uuid`
- `mic/<node_uuid>/status/streaming`
- `mic/<node_uuid>/status/rssi`
- `mic/<node_uuid>/status/uptime`
- `mic/<node_uuid>/status/packets_sent`
- `mic/<node_uuid>/status/packets_dropped`
- `mic/<node_uuid>/status/udp_target`

### Commands

- `mic/<node_uuid>/cmd/streaming/set`
- `mic/<node_uuid>/cmd/restart`
- `mic/<node_uuid>/cmd/udp_target/set`

## Timebase

All hub queries use `pc_receive_time`.

They do not use the embedded packet timestamp as the query timebase.

## Legacy HTTP API

The legacy HTTP API is deprecated and disabled by default, but while enabled it exposes:

- `GET /nodes`
- `POST /query/audio`
- `POST /query/stt`
- `GET /jobs/<job_id>`

Successful STT jobs may return:

- job status
- clip path
- ASR text
- empty `segments` for current `Qwen3-ASR` integration
