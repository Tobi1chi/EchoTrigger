from __future__ import annotations

from pathlib import Path


class ClipStorage:
    def __init__(self, clip_dir: Path) -> None:
        self._clip_dir = clip_dir
        self._clip_dir.mkdir(parents=True, exist_ok=True)

    @property
    def clip_dir(self) -> Path:
        return self._clip_dir

    def build_clip_path(self, node_uuid: str, start_time: float, end_time: float) -> Path:
        safe_uuid = node_uuid.replace("/", "_")
        file_name = f"{safe_uuid}_{start_time:.3f}_{end_time:.3f}.wav"
        return self._clip_dir / file_name
