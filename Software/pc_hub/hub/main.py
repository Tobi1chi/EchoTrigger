from __future__ import annotations

import logging

from hub.api import build_server
from hub.config import load_config
from hub.extractor import AudioExtractor
from hub.receiver import UdpReceiver
from hub.registry import NodeRegistry
from hub.ring_buffer import RingBufferStore
from hub.storage import ClipStorage


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    registry = NodeRegistry()
    ring_buffers = RingBufferStore(config.ring_minutes * 60)
    storage = ClipStorage(config.clip_dir)
    extractor = AudioExtractor(ring_buffers, storage)
    receiver = UdpReceiver(
        bind_host=config.udp_host,
        bind_port=config.udp_port,
        registry=registry,
        ring_buffers=ring_buffers,
    )
    receiver.start()
    logging.getLogger("pc_hub").info(
        "Listening for UDP audio on %s:%d and HTTP on http://%s:%d",
        config.udp_host,
        config.udp_port,
        config.bind_host,
        config.http_port,
    )
    logging.getLogger("pc_hub").info("Using worker at %s", config.worker_url)
    server = build_server(
        config.bind_host,
        config.http_port,
        extractor=extractor,
        registry=registry,
        worker_url=config.worker_url,
    )
    try:
        server.serve_forever()
    finally:
        receiver.stop()


if __name__ == "__main__":
    main()
