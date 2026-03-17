from __future__ import annotations

from pathlib import Path

from hub.models import AudioQueryResponse
from hub.ring_buffer import BufferedChunk, RingBufferStore
from hub.storage import ClipStorage
from shared.wav import write_pcm_wav


class AudioExtractor:
    def __init__(self, ring_buffers: RingBufferStore, storage: ClipStorage) -> None:
        self._ring_buffers = ring_buffers
        self._storage = storage

    def extract_audio(
        self,
        *,
        node_uuid: str,
        node_id: str,
        start_time: float,
        end_time: float,
    ) -> AudioQueryResponse:
        chunks = self._ring_buffers.extract(node_uuid, start_time, end_time)
        if not chunks:
            raise ValueError("no audio found in requested window")

        total_bytes = sum(len(chunk.samples) for chunk in chunks)
        pcm_buffer = bytearray(total_bytes)
        offset = 0
        for chunk in chunks:
            next_offset = offset + len(chunk.samples)
            pcm_buffer[offset:next_offset] = chunk.samples
            offset = next_offset
        first = chunks[0]
        duration = sum(chunk.duration_seconds for chunk in chunks)
        clip_path = self._storage.build_clip_path(node_uuid, start_time, end_time)
        write_pcm_wav(
            clip_path,
            bytes(pcm_buffer),
            channels=first.channels,
            sample_width_bytes=max(first.bits_per_sample // 8, 1),
            sample_rate=first.sample_rate,
        )
        self._storage.write_metadata(
            clip_path,
            node_uuid=node_uuid,
            start_time=start_time,
            end_time=end_time,
        )
        return AudioQueryResponse(
            node_uuid=node_uuid,
            node_id=node_id,
            audio_path=str(clip_path),
            sample_rate=first.sample_rate,
            duration_seconds=duration,
            start_time=start_time,
            end_time=end_time,
        )
