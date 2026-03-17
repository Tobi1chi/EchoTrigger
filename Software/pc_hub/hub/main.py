from __future__ import annotations

import logging

from hub.api import build_server
from hub.config import load_config
from hub.runtime import HubRuntime


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    runtime = HubRuntime.from_config(config)
    runtime.start()
    logging.getLogger("pc_hub").info(
        "Listening for UDP audio on %s:%d and legacy HTTP on http://%s:%d",
        config.udp_host,
        config.udp_port,
        config.bind_host,
        config.http_port,
    )
    logging.getLogger("pc_hub").info("Using worker at %s", config.worker_url)
    logging.getLogger("pc_hub").info(
        "Clip TTL=%ss max_query=%ss stt_queue=%s",
        config.clip_ttl_seconds,
        config.max_query_seconds,
        config.stt_job_queue_size,
    )
    server = build_server(
        config.bind_host,
        config.http_port,
        services=runtime.services,
    )
    try:
        server.serve_forever()
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
