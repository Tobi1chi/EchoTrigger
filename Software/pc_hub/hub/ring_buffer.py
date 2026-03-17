from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from hub.models import AudioFrame


@dataclass(slots=True)
class BufferedChunk:
    arrival_time: float
    seq: int
    timestamp_us: int
    sample_rate: int
    channels: int
    bits_per_sample: int
    samples: bytes

    @property
    def duration_seconds(self) -> float:
        bytes_per_sample = max(self.bits_per_sample // 8, 1)
        sample_count = len(self.samples) / bytes_per_sample
        return sample_count / float(self.sample_rate)


class PerNodeRingBuffer:
    def __init__(self, max_seconds: float) -> None:
        self._max_seconds = max_seconds
        self._lock = threading.Lock()
        self._chunks: deque[BufferedChunk] = deque()
        self._cached_duration = 0.0

    def append(self, frame: AudioFrame) -> None:
        chunk = BufferedChunk(
            arrival_time=frame.arrival_time,
            seq=frame.seq,
            timestamp_us=frame.timestamp_us,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            bits_per_sample=frame.bits_per_sample,
            samples=frame.samples,
        )
        with self._lock:
            self._chunks.append(chunk)
            self._cached_duration += chunk.duration_seconds
            while self._cached_duration > self._max_seconds and self._chunks:
                removed = self._chunks.popleft()
                self._cached_duration -= removed.duration_seconds

    def extract(self, start_time: float, end_time: float) -> list[BufferedChunk]:
        with self._lock:
            selected = [
                chunk
                for chunk in self._chunks
                if start_time <= chunk.arrival_time <= end_time
            ]
        return selected


class RingBufferStore:
    def __init__(self, max_seconds: float) -> None:
        self._max_seconds = max_seconds
        self._lock = threading.Lock()
        self._buffers: dict[str, PerNodeRingBuffer] = {}

    def append(self, frame: AudioFrame) -> None:
        with self._lock:
            buffer = self._buffers.get(frame.node_uuid)
            if buffer is None:
                buffer = PerNodeRingBuffer(self._max_seconds)
                self._buffers[frame.node_uuid] = buffer
        buffer.append(frame)

    def extract(self, node_uuid: str, start_time: float, end_time: float) -> list[BufferedChunk]:
        with self._lock:
            buffer = self._buffers.get(node_uuid)
        if buffer is None:
            return []
        return buffer.extract(start_time, end_time)
