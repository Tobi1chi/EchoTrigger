from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from hub.jobs import SttJobManager
from hub.models import AudioQueryRequest, SttJobStatus
from hub.storage import ClipStorage


class _DummyExtractor:
    pass


class _DummyRegistry:
    pass


class JobsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.storage = ClipStorage(Path(self._tmpdir.name), ttl_seconds=1)
        self.manager = SttJobManager(
            extractor=_DummyExtractor(),
            registry=_DummyRegistry(),
            storage=self.storage,
            worker_url="http://worker.invalid/transcribe",
            max_queue_size=4,
            job_ttl_seconds=1,
        )

    def _make_request(self) -> AudioQueryRequest:
        return AudioQueryRequest(node_uuid="node-1", start_time=10.0, end_time=11.0)

    def _make_clip(self, name: str) -> str:
        clip_path = Path(self._tmpdir.name) / name
        clip_path.write_bytes(b"wav")
        clip_path.with_suffix(".json").write_text("{}", encoding="utf-8")
        old = time.time() - 10
        Path(clip_path).touch((old, old))
        clip_path.with_suffix(".json").touch((old, old))
        return str(clip_path)

    def test_cleanup_skips_clip_still_referenced_by_job(self) -> None:
        clip_path = self._make_clip("queued.wav")
        self.manager.submit(self._make_request(), node_id="node-a", audio_path=clip_path)

        deleted = self.storage.cleanup_expired(protected_paths=self.manager._protected_audio_paths())

        self.assertEqual(deleted, 0)
        self.assertTrue(Path(clip_path).exists())
        self.assertTrue(Path(clip_path).with_suffix(".json").exists())

    def test_expired_jobs_are_removed_after_second_ttl_window(self) -> None:
        clip_path = self._make_clip("done.wav")
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
        self.manager._jobs[job.job_id] = job

        self.manager._expire_old_jobs()
        expired_job = self.manager._jobs[job.job_id]
        self.assertEqual(expired_job.status, "expired")
        self.assertIsNone(expired_job.audio_path)
        self.assertFalse(Path(clip_path).exists())

        expired_job.updated_at = time.time() - 2
        self.manager._expire_old_jobs()

        self.assertNotIn(job.job_id, self.manager._jobs)


if __name__ == "__main__":
    unittest.main()
