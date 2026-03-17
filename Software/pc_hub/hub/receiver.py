from __future__ import annotations

import logging
import socket
import threading
import time

from hub.protocol import parse_audio_packet
from hub.registry import NodeRegistry
from hub.ring_buffer import RingBufferStore


class UdpReceiver:
    def __init__(
        self,
        *,
        bind_host: str,
        bind_port: int,
        registry: NodeRegistry,
        ring_buffers: RingBufferStore,
    ) -> None:
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._registry = registry
        self._ring_buffers = ring_buffers
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logger = logging.getLogger("pc_hub.receiver")

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self._bind_host, self._bind_port))
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._run, name="udp-receiver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            self._sock.close()

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop_event.is_set():
            try:
                data, _addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return

            arrival_time = time.time()
            try:
                frame = parse_audio_packet(data, arrival_time)
            except ValueError as exc:
                self._logger.warning("Dropping invalid packet: %s", exc)
                continue

            self._registry.register_frame(frame)
            self._ring_buffers.append(frame)
