from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class AudioFrame:
    node_uuid: str
    node_id: str
    seq: int
    timestamp_us: int
    sample_rate: int
    channels: int
    bits_per_sample: int
    payload_bytes: int
    samples: bytes
    arrival_time: float

    @property
    def duration_seconds(self) -> float:
        bytes_per_sample = max(self.bits_per_sample // 8, 1)
        sample_count = self.payload_bytes / bytes_per_sample
        return sample_count / float(self.sample_rate)


@dataclass(slots=True)
class NodeState:
    node_uuid: str
    node_id: str
    last_seen: float
    last_seq: int
    packets_received: int = 0
    packets_missing: int = 0
    packets_out_of_order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AudioQueryRequest:
    node_uuid: str
    start_time: float
    end_time: float
    modality: str = "audio"


@dataclass(slots=True)
class AudioQueryResponse:
    node_uuid: str
    node_id: str
    audio_path: str
    sample_rate: int
    duration_seconds: float
    start_time: float
    end_time: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SttJobRequest:
    job_id: str
    audio_path: str
    node_uuid: str
    node_id: str
    start_time: float
    end_time: float
    modality: str = "audio"


@dataclass(slots=True)
class SttSegment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SttJobResponse:
    job_id: str
    status: str
    text: str
    segments: list[SttSegment] = field(default_factory=list)
    language: str | None = None
    duration_seconds: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data


@dataclass(slots=True)
class SttJobStatus:
    job_id: str
    status: str
    node_uuid: str
    node_id: str
    start_time: float
    end_time: float
    created_at: float
    updated_at: float
    audio_path: str | None = None
    text: str = ""
    segments: list[SttSegment] = field(default_factory=list)
    language: str | None = None
    duration_seconds: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data
