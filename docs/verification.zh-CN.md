# 验证

## Worker 冒烟测试

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

## MCP 运行检查

推荐路径：

1. 启动 `worker.main`
2. 启动 `mcp_adapter.main`
3. 让你的 MCP 客户端连接 `http://127.0.0.1:8767/mcp`

主要 MCP 工具：

- `list_nodes`
- `submit_stt_job`
- `get_stt_job`

## 可选的 Legacy HTTP 检查

使用这些端点前，需要显式启用 legacy API：

```sh
export PC_HUB_ENABLE_LEGACY_HTTP=1
python3 -m hub.main
```

然后验证：

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

轮询返回任务：

```sh
curl http://127.0.0.1:8765/jobs/<job_id>
```

## 模拟上行验证状态

这个仓库已经通过模拟 `ESP32` 上行做过验证：

- 把源音频转成 WAV
- 切成 `20 ms` PCM 包
- 通过当前固件包格式走 UDP 上传
- hub 正确注册模拟节点
- legacy `/query/audio` 成功
- legacy 异步 `/query/stt` 流程成功

已验证链路：

```text
音频文件 -> 模拟 UDP 包 -> pc_hub -> ring buffer -> WAV 提取 -> Qwen3-ASR -> 文本
```
