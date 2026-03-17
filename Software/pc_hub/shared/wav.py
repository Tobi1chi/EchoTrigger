from __future__ import annotations

import wave
from pathlib import Path


def write_pcm_wav(
    path: Path,
    pcm_bytes: bytes,
    *,
    channels: int,
    sample_width_bytes: int,
    sample_rate: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width_bytes)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
