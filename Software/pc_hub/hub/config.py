from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HubConfig:
    bind_host: str
    http_port: int
    legacy_http_enabled: bool
    udp_host: str
    udp_port: int
    ring_minutes: int
    clip_dir: Path
    worker_url: str
    clip_ttl_seconds: int
    max_query_seconds: int
    stt_job_queue_size: int
    stt_job_ttl_seconds: int
    mcp_bind_host: str
    mcp_port: int
    mcp_path: str
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_client_id: str
    ha_discovery_prefix: str
    mqtt_topic_prefix: str
    node_offline_seconds: int


def load_config() -> HubConfig:
    base_dir = Path(__file__).resolve().parent.parent
    default_clip_dir = base_dir / "runtime" / "clips"
    return HubConfig(
        bind_host=os.getenv("PC_HUB_BIND_HOST", "127.0.0.1"),
        http_port=int(os.getenv("PC_HUB_HTTP_PORT", "8765")),
        legacy_http_enabled=os.getenv("PC_HUB_ENABLE_LEGACY_HTTP", "0").strip().lower() in {"1", "true", "yes", "on"},
        udp_host=os.getenv("PC_HUB_UDP_HOST", "0.0.0.0"),
        udp_port=int(os.getenv("PC_HUB_UDP_PORT", "4000")),
        ring_minutes=int(os.getenv("PC_HUB_RING_MINUTES", "10")),
        clip_dir=Path(os.getenv("PC_HUB_CLIP_DIR", default_clip_dir)),
        worker_url=os.getenv("PC_HUB_WORKER_URL", "http://127.0.0.1:8766/transcribe"),
        clip_ttl_seconds=int(os.getenv("PC_HUB_CLIP_TTL_SECONDS", "900")),
        max_query_seconds=int(os.getenv("PC_HUB_MAX_QUERY_SECONDS", "120")),
        stt_job_queue_size=int(os.getenv("PC_HUB_STT_JOB_QUEUE_SIZE", "16")),
        stt_job_ttl_seconds=int(os.getenv("PC_HUB_STT_JOB_TTL_SECONDS", "900")),
        mcp_bind_host=os.getenv("PC_HUB_MCP_BIND_HOST", "127.0.0.1"),
        mcp_port=int(os.getenv("PC_HUB_MCP_PORT", "8767")),
        mcp_path=os.getenv("PC_HUB_MCP_PATH", "/mcp"),
        mqtt_host=os.getenv("PC_HUB_MQTT_HOST", "").strip(),
        mqtt_port=int(os.getenv("PC_HUB_MQTT_PORT", "1883")),
        mqtt_username=_nullable_env("PC_HUB_MQTT_USERNAME"),
        mqtt_password=_nullable_env("PC_HUB_MQTT_PASSWORD"),
        mqtt_client_id=os.getenv("PC_HUB_MQTT_CLIENT_ID", "pc-audio-hub"),
        ha_discovery_prefix=os.getenv("PC_HUB_HA_DISCOVERY_PREFIX", "homeassistant"),
        mqtt_topic_prefix=os.getenv("PC_HUB_MQTT_TOPIC_PREFIX", "mic_hub"),
        node_offline_seconds=int(os.getenv("PC_HUB_NODE_OFFLINE_SECONDS", "30")),
    )


def _nullable_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None
