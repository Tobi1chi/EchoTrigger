from __future__ import annotations

import json
import time
from pathlib import Path


class ClipStorage:
    def __init__(self, clip_dir: Path, *, ttl_seconds: int) -> None:
        self._clip_dir = clip_dir
        self._ttl_seconds = ttl_seconds
        self._clip_dir.mkdir(parents=True, exist_ok=True)

    @property
    def clip_dir(self) -> Path:
        return self._clip_dir

    def build_clip_path(self, node_uuid: str, start_time: float, end_time: float) -> Path:
        safe_uuid = node_uuid.replace("/", "_")
        node_dir = self._clip_dir / safe_uuid
        node_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{safe_uuid}_{start_time:.3f}_{end_time:.3f}.wav"
        return node_dir / file_name

    def write_metadata(self, clip_path: Path, *, node_uuid: str, start_time: float, end_time: float) -> None:
        metadata_path = clip_path.with_suffix(".json")
        payload = {
            "node_uuid": node_uuid,
            "start_time": start_time,
            "end_time": end_time,
            "created_at": time.time(),
            "clip_path": str(clip_path),
        }
        metadata_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def delete_clip(self, clip_path: str | Path) -> None:
        path = Path(clip_path)
        for candidate in (path, path.with_suffix(".json")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                continue

    def cleanup_expired(self) -> int:
        cutoff = time.time() - self._ttl_seconds
        deleted = 0
        for wav_path in self._clip_dir.rglob("*.wav"):
            try:
                if wav_path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            self.delete_clip(wav_path)
            deleted += 1
        return deleted
