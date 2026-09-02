# Verification

## Worker Smoke Test

```powershell
$body = @{
  job_id = "manual-test"
  audio_path = "./path/to/audio.wav"
  node_uuid = "manual-node"
  node_id = "manual-node"
  start_time = 0
  end_time = 1
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8766/transcribe" -ContentType "application/json" -Body $body
```

JSON payload:

```json
{
    "job_id":"manual-test",
    "audio_path":"./path/to/audio.wav",
    "node_uuid":"manual-node",
    "node_id":"manual-node",
    "start_time":0,
    "end_time":1
}
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

```powershell
$env:PC_HUB_ENABLE_LEGACY_HTTP="1"
uv run python -m hub.main
```

Then validate:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/nodes"
```

```powershell
$body = @{
  node_uuid = "esp32s3-xxxxxxxxxxxx"
  start_time = 1710000000.1
  end_time = 1710000030.1
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/query/stt" -ContentType "application/json" -Body $body
```

JSON payload:

```json
{
    "node_uuid":"esp32s3-xxxxxxxxxxxx",
    "start_time":1710000000.1,
    "end_time":1710000030.1
}
```

Poll the returned job:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/jobs/<job_id>"
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
audio file -> simulated UDP packets -> pc_hub -> ring buffer -> WAV extraction -> ASR worker -> text
```
