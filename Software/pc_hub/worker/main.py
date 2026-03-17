from __future__ import annotations

import logging
import os

from worker.api import build_server
from worker.backends import Qwen3AsrBackend
from worker.backends.base import SttBackend
from worker.backends.qwen3_asr import Qwen3AsrConfig, default_device_map, default_dtype


def build_backend() -> SttBackend:
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.getenv("PC_HUB_WORKER_HOST", "127.0.0.1")
    port = int(os.getenv("PC_HUB_WORKER_PORT", "8766"))
    adapter = build_backend()
    server = build_server(host, port, adapter)
    logging.getLogger("pc_hub.worker").info(
        "Starting ASR worker on http://%s:%d using model=%s",
        host,
        port,
        os.getenv("PC_HUB_ASR_MODEL", "Qwen/Qwen3-ASR-0.6B"),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
