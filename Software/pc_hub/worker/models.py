from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class WorkerSegment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class WorkerResponse:
    job_id: str
    status: str
    text: str
    segments: list[WorkerSegment]
    language: str | None
    duration_seconds: float | None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data
