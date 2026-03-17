from __future__ import annotations

import platform
import wave
from dataclasses import dataclass

import torch

from worker.models import WorkerResponse


@dataclass(frozen=True)
class Qwen3AsrConfig:
    model_name: str
    language: str | None
    device_map: str
    dtype: str
    max_inference_batch_size: int
    max_new_tokens: int


class Qwen3AsrBackend:
    def __init__(self, config: Qwen3AsrConfig) -> None:
        self._config = config
        self._model = None
        self._resolved_device_map: str | None = None

    def transcribe(self, *, job_id: str, audio_path: str) -> WorkerResponse:
        try:
            model = self._get_model()
            results = model.transcribe(
                audio_path,
                language=_normalize_language(self._config.language),
            )
        except ModuleNotFoundError as exc:
            return self._error(job_id, audio_path, f"qwen-asr is not installed: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._error(job_id, audio_path, f"qwen3-asr transcription failed: {exc}")

        if not results:
            return self._error(job_id, audio_path, "qwen3-asr returned no results")

        first = results[0]
        return WorkerResponse(
            job_id=job_id,
            status="ok",
            text=(first.text or "").strip(),
            segments=[],
            language=getattr(first, "language", None),
            duration_seconds=_wav_duration(audio_path),
            error=None,
        )

    def _get_model(self):
        if self._model is None:
            from qwen_asr import Qwen3ASRModel

            last_error: Exception | None = None
            for device_map in _candidate_device_maps(self._config.device_map):
                try:
                    self._model = Qwen3ASRModel.from_pretrained(
                        self._config.model_name,
                        dtype=_resolve_dtype(self._config.dtype),
                        device_map=device_map,
                        max_inference_batch_size=self._config.max_inference_batch_size,
                        max_new_tokens=self._config.max_new_tokens,
                    )
                    self._resolved_device_map = device_map
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc

            if self._model is None and last_error is not None:
                raise last_error
        return self._model

    def _error(self, job_id: str, audio_path: str, message: str) -> WorkerResponse:
        return WorkerResponse(
            job_id=job_id,
            status="error",
            text="",
            segments=[],
            language=None,
            duration_seconds=_wav_duration(audio_path),
            error=message,
        )


def default_device_map() -> str:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mps"
    if platform.system() == "Windows":
        return "auto"
    return "cpu"


def default_dtype() -> str:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "float16"
    return "float32"


def _resolve_dtype(name: str) -> torch.dtype:
    normalized = name.strip().lower()
    if normalized == "float16":
        return torch.float16
    if normalized == "float32":
        return torch.float32
    if normalized == "bfloat16":
        return torch.bfloat16
    raise ValueError(f"Unsupported torch dtype: {name}")


def _candidate_device_maps(device_map: str) -> tuple[str, ...]:
    normalized = device_map.strip().lower()
    if normalized != "auto":
        return (device_map,)

    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return ("mps",)

    if platform.system() == "Windows" and torch.cuda.is_available():
        return ("cuda", "cpu")

    return ("cpu",)


def _normalize_language(name: str | None) -> str | None:
    if not name:
        return None
    mapping = {
        "zh": "Chinese",
        "cn": "Chinese",
        "en": "English",
        "yue": "Cantonese",
    }
    lowered = name.strip()
    return mapping.get(lowered.lower(), lowered)


def _wav_duration(audio_path: str) -> float:
    with wave.open(audio_path, "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
    return frames / float(rate)
