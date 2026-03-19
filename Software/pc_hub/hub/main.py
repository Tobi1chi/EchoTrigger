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
    if runtime.ha_bridge_running:
        logging.getLogger("pc_hub").info(
            "Home Assistant MQTT bridge enabled for %s:%d with topic prefix %s",
            config.mqtt_host,
            config.mqtt_port,
            config.mqtt_topic_prefix,
        )
    elif config.mqtt_host:
        logging.getLogger("pc_hub").warning(
            "Home Assistant MQTT bridge is configured for %s:%d but is not running; continuing without HA integration",
            config.mqtt_host,
            config.mqtt_port,
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
