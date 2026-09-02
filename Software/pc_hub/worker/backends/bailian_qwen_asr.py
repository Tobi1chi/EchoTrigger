from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.models import WorkerResponse


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-asr-flash"
MAX_INLINE_AUDIO_BYTES = 7_500_000


@dataclass(frozen=True)
class BailianQwenAsrConfig:
    api_key: str | None
    base_url: str
    model_name: str
    language: str | None
    enable_itn: bool
    timeout_seconds: float
    max_audio_bytes: int


class BailianQwenAsrBackend:
    def __init__(self, config: BailianQwenAsrConfig) -> None:
        self._config = config

    def transcribe(self, *, job_id: str, audio_path: str) -> WorkerResponse:
        if not self._config.api_key:
            return self._error(
                job_id,
                audio_path,
                "missing Bailian API key; set PC_HUB_BAILIAN_API_KEY or DASHSCOPE_API_KEY",
            )

        try:
            payload = _build_payload(audio_path, self._config)
            raw_response = _post_json(
                _chat_completions_url(self._config.base_url),
                payload,
                api_key=self._config.api_key,
                timeout_seconds=self._config.timeout_seconds,
            )
            text, language = _parse_openai_compatible_response(raw_response, self._config.language)
        except Exception as exc:  # noqa: BLE001
            return self._error(job_id, audio_path, f"Bailian Qwen ASR transcription failed: {exc}")

        if not text:
            return self._error(job_id, audio_path, "Bailian Qwen ASR returned empty text")

        return WorkerResponse(
            job_id=job_id,
            status="ok",
            text=text,
            segments=[],
            language=language,
            duration_seconds=_wav_duration(audio_path),
            error=None,
        )

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


def _build_payload(audio_path: str, config: BailianQwenAsrConfig) -> dict[str, Any]:
    path = Path(audio_path)
    audio_bytes = path.read_bytes()
    if len(audio_bytes) > config.max_audio_bytes:
        raise ValueError(
            f"audio file is {len(audio_bytes)} bytes, above inline Bailian limit "
            f"{config.max_audio_bytes} bytes"
        )

    data_uri = f"data:{_audio_mime_type(path)};base64,{base64.b64encode(audio_bytes).decode('ascii')}"
    asr_options: dict[str, Any] = {"enable_itn": config.enable_itn}
    if config.language:
        asr_options["language"] = config.language

    return {
        "model": config.model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": data_uri,
                            "format": _audio_format(path),
                        },
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": asr_options,
    }


def _post_json(url: str, payload: dict[str, Any], *, api_key: str, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc

    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Bailian response is not a JSON object")
    return parsed


def _parse_openai_compatible_response(response: dict[str, Any], default_language: str | None) -> tuple[str, str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices in Bailian response")

    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("invalid choice in Bailian response")

    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("missing message in Bailian response")

    text = _message_content_to_text(message.get("content")).strip()
    language = _first_annotation_value(message.get("annotations"), "language") or default_language
    return text, language


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _first_annotation_value(annotations: object, key: str) -> str | None:
    if not isinstance(annotations, list):
        return None
    for annotation in annotations:
        if isinstance(annotation, dict) and isinstance(annotation.get(key), str):
            return annotation[key]
    return None


def _chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _audio_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
    }
    return mapping.get(suffix, "application/octet-stream")


def _audio_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "opus":
        return "ogg"
    return suffix or "wav"


def _wav_duration(audio_path: str) -> float | None:
    try:
        with wave.open(audio_path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
        return frames / float(rate)
    except (wave.Error, OSError, EOFError):
        return None
