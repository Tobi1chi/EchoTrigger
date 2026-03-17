from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HubConfig:
    bind_host: str
    http_port: int
    udp_host: str
    udp_port: int
    ring_minutes: int
    clip_dir: Path
    worker_url: str
    clip_ttl_seconds: int
    max_query_seconds: int
    stt_job_queue_size: int
    stt_job_ttl_seconds: int


def load_config() -> HubConfig:
    base_dir = Path(__file__).resolve().parent.parent
    default_clip_dir = base_dir / "runtime" / "clips"
    return HubConfig(
        bind_host=os.getenv("PC_HUB_BIND_HOST", "127.0.0.1"),
        http_port=int(os.getenv("PC_HUB_HTTP_PORT", "8765")),
        udp_host=os.getenv("PC_HUB_UDP_HOST", "0.0.0.0"),
        udp_port=int(os.getenv("PC_HUB_UDP_PORT", "4000")),
        ring_minutes=int(os.getenv("PC_HUB_RING_MINUTES", "10")),
        clip_dir=Path(os.getenv("PC_HUB_CLIP_DIR", default_clip_dir)),
        worker_url=os.getenv("PC_HUB_WORKER_URL", "http://127.0.0.1:8766/transcribe"),
        clip_ttl_seconds=int(os.getenv("PC_HUB_CLIP_TTL_SECONDS", "900")),
        max_query_seconds=int(os.getenv("PC_HUB_MAX_QUERY_SECONDS", "120")),
        stt_job_queue_size=int(os.getenv("PC_HUB_STT_JOB_QUEUE_SIZE", "16")),
        stt_job_ttl_seconds=int(os.getenv("PC_HUB_STT_JOB_TTL_SECONDS", "900")),
    )
