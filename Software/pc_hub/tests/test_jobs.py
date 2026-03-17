from __future__ import annotations

import time
from pathlib import Path

import pytest

from hub.jobs import SttJobManager
from hub.models import AudioQueryRequest, SttJobStatus
from hub.storage import ClipStorage


class _DummyExtractor:
    pass


class _DummyRegistry:
    pass


@pytest.fixture
def storage(tmp_path: Path) -> ClipStorage:
    return ClipStorage(tmp_path, ttl_seconds=1)


@pytest.fixture
def manager(storage: ClipStorage) -> SttJobManager:
    return SttJobManager(
        extractor=_DummyExtractor(),
        registry=_DummyRegistry(),
        storage=storage,
        worker_url="http://worker.invalid/transcribe",
        max_queue_size=4,
        job_ttl_seconds=1,
    )


@pytest.fixture
def audio_request() -> AudioQueryRequest:
    return AudioQueryRequest(node_uuid="node-1", start_time=10.0, end_time=11.0)


def _make_clip(base_dir: Path, name: str) -> str:
    clip_path = base_dir / name
    clip_path.write_bytes(b"wav")
    clip_path.with_suffix(".json").write_text("{}", encoding="utf-8")
    old = time.time() - 10
    clip_path.touch((old, old))
    clip_path.with_suffix(".json").touch((old, old))
    return str(clip_path)


def test_cleanup_skips_clip_still_referenced_by_job(
    tmp_path: Path,
    storage: ClipStorage,
    manager: SttJobManager,
    audio_request: AudioQueryRequest,
) -> None:
    clip_path = _make_clip(tmp_path, "queued.wav")
    manager.submit(audio_request, node_id="node-a", audio_path=clip_path)

    deleted = storage.cleanup_expired(protected_paths=manager._protected_audio_paths())

    assert deleted == 0
    assert Path(clip_path).exists()
    assert Path(clip_path).with_suffix(".json").exists()


def test_expired_jobs_are_removed_after_second_ttl_window(
    tmp_path: Path,
    manager: SttJobManager,
) -> None:
    clip_path = _make_clip(tmp_path, "done.wav")
    now = time.time()
    job = SttJobStatus(
        job_id="job-1",
        status="succeeded",
        node_uuid="node-1",
        node_id="node-a",
        start_time=10.0,
        end_time=11.0,
        created_at=now - 5,
        updated_at=now - 5,
        audio_path=clip_path,
        text="hello",
    )
    manager._jobs[job.job_id] = job

    manager._expire_old_jobs()
    expired_job = manager._jobs[job.job_id]
    assert expired_job.status == "expired"
    assert expired_job.audio_path is None
    assert not Path(clip_path).exists()

    expired_job.updated_at = time.time() - 2
    manager._expire_old_jobs()

    assert job.job_id not in manager._jobs
