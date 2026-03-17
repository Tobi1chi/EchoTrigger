from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import replace

from hub.extractor import AudioExtractor
from hub.models import AudioQueryRequest, SttJobRequest, SttJobStatus
from hub.registry import NodeRegistry
from hub.storage import ClipStorage


class JobQueueFullError(RuntimeError):
    pass


class JobNotFoundError(RuntimeError):
    pass


class SttJobManager:
    def __init__(
        self,
        *,
        extractor: AudioExtractor,
        registry: NodeRegistry,
        storage: ClipStorage,
        worker_url: str,
        max_queue_size: int,
        job_ttl_seconds: int,
    ) -> None:
        self._extractor = extractor
        self._registry = registry
        self._storage = storage
        self._worker_url = worker_url
        self._job_ttl_seconds = job_ttl_seconds
        self._queue: queue.Queue[tuple[str, AudioQueryRequest, str]] = queue.Queue(maxsize=max_queue_size)
        self._jobs: dict[str, SttJobStatus] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._run, name="pc_hub_stt_jobs", daemon=True)
        self._logger = logging.getLogger("pc_hub.jobs")

    def start(self) -> None:
        self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._worker_thread.join(timeout=2)

    def submit(self, request: AudioQueryRequest, *, node_id: str) -> SttJobStatus:
        self._expire_old_jobs()
        job_id = str(uuid.uuid4())
        now = time.time()
        job = SttJobStatus(
            job_id=job_id,
            status="queued",
            node_uuid=request.node_uuid,
            node_id=node_id,
            start_time=request.start_time,
            end_time=request.end_time,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = job
        try:
            self._queue.put_nowait((job_id, request, node_id))
        except queue.Full as exc:
            with self._lock:
                self._jobs.pop(job_id, None)
            raise JobQueueFullError("stt job queue is full") from exc
        return replace(job)

    def get(self, job_id: str) -> SttJobStatus:
        self._expire_old_jobs()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            return replace(job)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id, request, node_id = self._queue.get(timeout=1)
            except queue.Empty:
                self._storage.cleanup_expired()
                self._expire_old_jobs()
                continue

            self._set_status(job_id, status="running")
            try:
                audio_response = self._extractor.extract_audio(
                    node_uuid=request.node_uuid,
                    node_id=node_id,
                    start_time=request.start_time,
                    end_time=request.end_time,
                )
                self._set_status(job_id, audio_path=audio_response.audio_path)

                worker_response = _call_worker(
                    self._worker_url,
                    SttJobRequest(
                        job_id=job_id,
                        audio_path=audio_response.audio_path,
                        node_uuid=request.node_uuid,
                        node_id=node_id,
                        start_time=request.start_time,
                        end_time=request.end_time,
                    ),
                )
                self._set_status(
                    job_id,
                    status="succeeded" if worker_response.get("status") == "ok" else "failed",
                    text=str(worker_response.get("text", "")),
                    segments=list(worker_response.get("segments", [])),
                    language=_maybe_str(worker_response.get("language")),
                    duration_seconds=_maybe_float(worker_response.get("duration_seconds")),
                    error=_maybe_str(worker_response.get("error")),
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.exception("STT job %s failed", job_id)
                self._set_status(job_id, status="failed", error=str(exc))
            finally:
                self._queue.task_done()
                self._storage.cleanup_expired()
                self._expire_old_jobs()

    def _set_status(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                if key == "segments":
                    value = [_segment_from_dict(item) for item in value]  # type: ignore[arg-type]
                setattr(job, key, value)
            job.updated_at = time.time()

    def _expire_old_jobs(self) -> None:
        now = time.time()
        with self._lock:
            for job in self._jobs.values():
                if job.status in {"queued", "running"}:
                    continue
                if now - job.updated_at < self._job_ttl_seconds:
                    continue
                if job.status != "expired":
                    if job.audio_path:
                        self._storage.delete_clip(job.audio_path)
                        job.audio_path = None
                    job.status = "expired"
                    job.text = ""
                    job.segments = []
                    job.language = None
                    job.duration_seconds = None
                    job.error = "job result expired"
                    job.updated_at = now


def _segment_from_dict(item: object):
    from hub.models import SttSegment

    if not isinstance(item, dict):
        return SttSegment(start=0.0, end=0.0, text="")
    return SttSegment(
        start=float(item.get("start", 0.0)),
        end=float(item.get("end", 0.0)),
        text=str(item.get("text", "")),
    )


def _maybe_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _call_worker(worker_url: str, request: SttJobRequest) -> dict[str, object]:
    payload = json.dumps(
        {
            "job_id": request.job_id,
            "audio_path": request.audio_path,
            "node_uuid": request.node_uuid,
            "node_id": request.node_id,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "modality": request.modality,
        }
    ).encode("utf-8")
    http_request = urllib.request.Request(
        worker_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"worker request failed: {exc}") from exc
