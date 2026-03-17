from __future__ import annotations

from dataclasses import dataclass

from hub.config import HubConfig
from hub.extractor import AudioExtractor
from hub.jobs import SttJobManager
from hub.receiver import UdpReceiver
from hub.registry import NodeRegistry
from hub.ring_buffer import RingBufferStore
from hub.services import HubServices
from hub.storage import ClipStorage


@dataclass(slots=True)
class HubRuntime:
    config: HubConfig
    registry: NodeRegistry
    ring_buffers: RingBufferStore
    storage: ClipStorage
    extractor: AudioExtractor
    jobs: SttJobManager
    receiver: UdpReceiver
    services: HubServices

    @classmethod
    def from_config(cls, config: HubConfig) -> HubRuntime:
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
        services = HubServices(
            extractor=extractor,
            registry=registry,
            jobs=jobs,
            max_query_seconds=config.max_query_seconds,
        )
        return cls(
            config=config,
            registry=registry,
            ring_buffers=ring_buffers,
            storage=storage,
            extractor=extractor,
            jobs=jobs,
            receiver=receiver,
            services=services,
        )

    def start(self) -> None:
        self.receiver.start()
        self.jobs.start()

    def stop(self) -> None:
        self.jobs.stop()
        self.receiver.stop()
