from __future__ import annotations

import logging
import os

from worker.api import build_server
from worker.backends import BailianQwenAsrBackend, Qwen3AsrBackend
from worker.backends.base import SttBackend
from worker.backends.bailian_qwen_asr import (
    BailianQwenAsrConfig,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MAX_INLINE_AUDIO_BYTES,
)
from worker.backends.qwen3_asr import Qwen3AsrConfig, default_device_map, default_dtype


def build_backend() -> SttBackend:
    provider = os.getenv("PC_HUB_ASR_PROVIDER", "bailian").strip().lower()
    if provider in {"bailian", "aliyun", "dashscope", "cloud-qwen3"}:
        return BailianQwenAsrBackend(
            BailianQwenAsrConfig(
                api_key=os.getenv("PC_HUB_BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
                base_url=_bailian_base_url(),
                model_name=os.getenv("PC_HUB_BAILIAN_MODEL", DEFAULT_MODEL),
                language=_nullable_env("PC_HUB_ASR_LANGUAGE", "zh"),
                enable_itn=_bool_env("PC_HUB_BAILIAN_ENABLE_ITN", False),
                timeout_seconds=float(os.getenv("PC_HUB_BAILIAN_TIMEOUT_SECONDS", "60")),
                max_audio_bytes=int(os.getenv("PC_HUB_BAILIAN_MAX_AUDIO_BYTES", str(MAX_INLINE_AUDIO_BYTES))),
            )
        )

    if provider not in {"local-qwen3", "qwen3", "local"}:
        raise ValueError(f"Unsupported PC_HUB_ASR_PROVIDER: {provider}")

    return Qwen3AsrBackend(
        Qwen3AsrConfig(
            model_name=os.getenv("PC_HUB_ASR_MODEL", "Qwen/Qwen3-ASR-0.6B"),
            language=_nullable_env("PC_HUB_ASR_LANGUAGE", "zh"),
            device_map=os.getenv("PC_HUB_ASR_DEVICE_MAP", default_device_map()),
            dtype=os.getenv("PC_HUB_ASR_DTYPE", default_dtype()),
            max_inference_batch_size=int(os.getenv("PC_HUB_ASR_MAX_BATCH_SIZE", "1")),
            max_new_tokens=int(os.getenv("PC_HUB_ASR_MAX_NEW_TOKENS", "512")),
        )
    )


def _nullable_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value if value else None


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bailian_base_url() -> str:
    explicit = _nullable_env("PC_HUB_BAILIAN_BASE_URL")
    if explicit:
        return explicit

    workspace_id = _nullable_env("PC_HUB_BAILIAN_WORKSPACE_ID")
    if workspace_id:
        region = os.getenv("PC_HUB_BAILIAN_REGION", "cn-beijing")
        return f"https://{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"

    return DEFAULT_BASE_URL


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.getenv("PC_HUB_WORKER_HOST", "127.0.0.1")
    port = int(os.getenv("PC_HUB_WORKER_PORT", "8766"))
    adapter = build_backend()
    provider = os.getenv("PC_HUB_ASR_PROVIDER", "bailian")
    server = build_server(host, port, adapter)
    logging.getLogger("pc_hub.worker").info(
        "Starting ASR worker on http://%s:%d using provider=%s model=%s",
        host,
        port,
        provider,
        os.getenv("PC_HUB_BAILIAN_MODEL")
        or os.getenv("PC_HUB_ASR_MODEL")
        or ("qwen3-asr-flash" if provider == "bailian" else "Qwen/Qwen3-ASR-0.6B"),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
