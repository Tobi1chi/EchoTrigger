# Verification

## Worker Smoke Test

```sh
curl -X POST http://127.0.0.1:8766/transcribe \
  -H 'Content-Type: application/json' \
  -d '{
    "job_id":"manual-test",
    "audio_path":"./path/to/audio.wav",
    "node_uuid":"manual-node",
    "node_id":"manual-node",
    "start_time":0,
    "end_time":1
  }'
```

## MCP Runtime Check

Recommended runtime:

1. start `worker.main`
2. start `mcp_adapter.main`
3. connect your MCP client to `http://127.0.0.1:8767/mcp`

Primary MCP tools:

- `list_nodes`
- `submit_stt_job`
- `get_stt_job`

## Optional Legacy HTTP Check

Enable the legacy API explicitly before using these endpoints:

```sh
export PC_HUB_ENABLE_LEGACY_HTTP=1
python3 -m hub.main
```

Then validate:

```sh
curl http://127.0.0.1:8765/nodes
```

```sh
curl -X POST http://127.0.0.1:8765/query/stt \
  -H 'Content-Type: application/json' \
  -d '{
    "node_uuid":"esp32s3-xxxxxxxxxxxx",
    "start_time":1710000000.1,
    "end_time":1710000030.1
  }'
```

Poll the returned job:

```sh
curl http://127.0.0.1:8765/jobs/<job_id>
```

## Simulated Uplink Status

This repository has already been validated with a simulated `ESP32` uplink:

- source audio converted to WAV
- split into `20 ms` PCM packets
- uploaded over UDP using the current firmware packet format
- hub registered the simulated node
- legacy `/query/audio` succeeded
- legacy async `/query/stt` flow succeeded

Verified chain:

```text
audio file -> simulated UDP packets -> pc_hub -> ring buffer -> WAV extraction -> Qwen3-ASR -> text
```
