from __future__ import annotations

from dataclasses import dataclass
import logging

from hub.config import HubConfig
from hub.extractor import AudioExtractor
from hub.ha_mqtt import HaMqttBridge, HaMqttBridgeConfig
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
    ha_bridge: HaMqttBridge | None

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
        ha_bridge_config = HaMqttBridgeConfig.from_hub_config(config)
        ha_bridge = HaMqttBridge(config=ha_bridge_config, registry=registry) if ha_bridge_config.enabled else None
        return cls(
            config=config,
            registry=registry,
            ring_buffers=ring_buffers,
            storage=storage,
            extractor=extractor,
            jobs=jobs,
            receiver=receiver,
            services=services,
            ha_bridge=ha_bridge,
        )

    def start(self) -> None:
        self.receiver.start()
        self.jobs.start()
        if self.ha_bridge is not None:
            try:
                self.ha_bridge.start()
            except Exception:
                logging.getLogger("pc_hub.runtime").exception(
                    "Home Assistant MQTT bridge failed to start; continuing without HA integration"
                )

    @property
    def ha_bridge_running(self) -> bool:
        return self.ha_bridge.is_running if self.ha_bridge is not None else False

    def stop(self) -> None:
        if self.ha_bridge is not None:
            self.ha_bridge.stop()
        self.jobs.stop()
        self.receiver.stop()
