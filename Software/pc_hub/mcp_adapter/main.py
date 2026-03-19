from __future__ import annotations

import logging
import threading

from hub.api import build_server
from hub.config import load_config
from hub.runtime import HubRuntime
from mcp_adapter.server import build_mcp_server


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    runtime = HubRuntime.from_config(config)
    runtime.start()

    legacy_server = None
    legacy_thread = None
    if config.legacy_http_enabled:
        legacy_server = build_server(config.bind_host, config.http_port, services=runtime.services)
        legacy_thread = threading.Thread(target=legacy_server.serve_forever, name="pc_hub_legacy_http", daemon=True)
        legacy_thread.start()
        logging.getLogger("pc_hub.mcp").info(
            "Legacy HTTP API enabled on http://%s:%d",
            config.bind_host,
            config.http_port,
        )

    logging.getLogger("pc_hub.mcp").info(
        "Listening for UDP audio on %s:%d and MCP on http://%s:%d%s",
        config.udp_host,
        config.udp_port,
        config.mcp_bind_host,
        config.mcp_port,
        config.mcp_path,
    )
    logging.getLogger("pc_hub.mcp").info("Using worker at %s", config.worker_url)
    if runtime.ha_bridge_running:
        logging.getLogger("pc_hub.mcp").info(
            "Home Assistant MQTT bridge enabled for %s:%d with topic prefix %s",
            config.mqtt_host,
            config.mqtt_port,
            config.mqtt_topic_prefix,
        )
    elif config.mqtt_host:
        logging.getLogger("pc_hub.mcp").warning(
            "Home Assistant MQTT bridge is configured for %s:%d but is not running; continuing without HA integration",
            config.mqtt_host,
            config.mqtt_port,
        )

    server = build_mcp_server(config, runtime.services)
    try:
        server.run(transport="streamable-http")
    finally:
        if legacy_server is not None:
            legacy_server.shutdown()
            if legacy_thread is not None:
                legacy_thread.join(timeout=2)
            legacy_server.server_close()
        runtime.stop()


if __name__ == "__main__":
    main()
