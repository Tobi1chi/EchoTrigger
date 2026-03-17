from __future__ import annotations

from typing import Protocol

from worker.models import WorkerResponse


class SttBackend(Protocol):
    def transcribe(self, *, job_id: str, audio_path: str) -> WorkerResponse:
        ...
