from __future__ import annotations

import logging

from hub.api import build_server
from hub.config import load_config
from hub.extractor import AudioExtractor
from hub.jobs import SttJobManager
from hub.receiver import UdpReceiver
from hub.registry import NodeRegistry
from hub.ring_buffer import RingBufferStore
from hub.storage import ClipStorage


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    registry = NodeRegistry()
    ring_buffers = RingBufferStore(config.ring_minutes * 60)
    storage = ClipStorage(config.clip_dir, ttl_seconds=config.clip_ttl_seconds)
    extractor = AudioExtractor(ring_buffers, storage)
    jobs = SttJobManager(
        extractor=extractor,
        registry=registry,
        storage=storage,
        worker_url=config.worker_url,
        max_queue_size=config.stt_job_queue_size,
        job_ttl_seconds=config.stt_job_ttl_seconds,
    )
    receiver = UdpReceiver(
        bind_host=config.udp_host,
        bind_port=config.udp_port,
        registry=registry,
        ring_buffers=ring_buffers,
    )
    receiver.start()
    jobs.start()
    logging.getLogger("pc_hub").info(
        "Listening for UDP audio on %s:%d and HTTP on http://%s:%d",
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
        extractor=extractor,
        registry=registry,
        jobs=jobs,
        max_query_seconds=config.max_query_seconds,
    )
    try:
        server.serve_forever()
    finally:
        jobs.stop()
        receiver.stop()


if __name__ == "__main__":
    main()
