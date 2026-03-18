FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY hub /app/hub
COPY mcp_adapter /app/mcp_adapter
COPY shared /app/shared
COPY worker /app/worker

RUN python -m pip install --upgrade pip \
    && python -m pip install .

ENV PC_HUB_BIND_HOST=0.0.0.0
ENV PC_HUB_HTTP_PORT=8765
ENV PC_HUB_ENABLE_LEGACY_HTTP=1
ENV PC_HUB_UDP_HOST=0.0.0.0
ENV PC_HUB_UDP_PORT=4000
ENV PC_HUB_RING_MINUTES=10
ENV PC_HUB_CLIP_DIR=/app/runtime/clips
ENV PC_HUB_WORKER_URL=http://worker:8766/transcribe
ENV PC_HUB_CLIP_TTL_SECONDS=900
ENV PC_HUB_MAX_QUERY_SECONDS=120
ENV PC_HUB_STT_JOB_QUEUE_SIZE=16
ENV PC_HUB_STT_JOB_TTL_SECONDS=900
ENV PC_HUB_MCP_BIND_HOST=0.0.0.0
ENV PC_HUB_MCP_PORT=8767
ENV PC_HUB_MCP_PATH=/mcp
ENV PC_HUB_WORKER_HOST=0.0.0.0
ENV PC_HUB_WORKER_PORT=8766
ENV PC_HUB_ASR_MODEL=Qwen/Qwen3-ASR-0.6B
ENV PC_HUB_ASR_LANGUAGE=zh
ENV PC_HUB_ASR_DEVICE_MAP=cpu
ENV PC_HUB_ASR_DTYPE=float32
ENV PC_HUB_ASR_MAX_BATCH_SIZE=1
ENV PC_HUB_ASR_MAX_NEW_TOKENS=512

RUN mkdir -p /app/runtime/clips

CMD ["python", "-m", "mcp_adapter.main"]
