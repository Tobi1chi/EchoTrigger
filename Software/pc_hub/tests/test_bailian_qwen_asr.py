from __future__ import annotations

import wave

from worker.backends import bailian_qwen_asr
from worker.backends.bailian_qwen_asr import BailianQwenAsrBackend, BailianQwenAsrConfig


def _write_wav(path) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)


def test_bailian_backend_posts_base64_audio(monkeypatch, tmp_path) -> None:
    wav_path = tmp_path / "clip.wav"
    _write_wav(wav_path)
    captured: dict[str, object] = {}

    def fake_post_json(url, payload, *, api_key, timeout_seconds):
        captured["url"] = url
        captured["payload"] = payload
        captured["api_key"] = api_key
        captured["timeout_seconds"] = timeout_seconds
        return {"choices": [{"message": {"content": "你好，世界"}}]}

    monkeypatch.setattr(bailian_qwen_asr, "_post_json", fake_post_json)

    backend = BailianQwenAsrBackend(
        BailianQwenAsrConfig(
            api_key="test-key",
            base_url="https://example.invalid/compatible-mode/v1/",
            model_name="qwen3-asr-flash",
            language="zh",
            enable_itn=True,
            timeout_seconds=12,
            max_audio_bytes=100_000,
        )
    )

    response = backend.transcribe(job_id="job-1", audio_path=str(wav_path))

    assert response.status == "ok"
    assert response.text == "你好，世界"
    assert response.language == "zh"
    assert response.duration_seconds == 0.01
    assert captured["url"] == "https://example.invalid/compatible-mode/v1/chat/completions"
    assert captured["api_key"] == "test-key"
    assert captured["timeout_seconds"] == 12
    payload = captured["payload"]
    assert payload["model"] == "qwen3-asr-flash"
    assert payload["asr_options"] == {"enable_itn": True, "language": "zh"}
    input_audio = payload["messages"][0]["content"][0]["input_audio"]
    assert input_audio["data"].startswith("data:audio/wav;base64,")
    assert input_audio["format"] == "wav"


def test_bailian_backend_reports_missing_api_key(tmp_path) -> None:
    wav_path = tmp_path / "clip.wav"
    _write_wav(wav_path)
    backend = BailianQwenAsrBackend(
        BailianQwenAsrConfig(
            api_key=None,
            base_url="https://example.invalid/compatible-mode/v1",
            model_name="qwen3-asr-flash",
            language="zh",
            enable_itn=False,
            timeout_seconds=60,
            max_audio_bytes=100_000,
        )
    )

    response = backend.transcribe(job_id="job-1", audio_path=str(wav_path))

    assert response.status == "error"
    assert "PC_HUB_BAILIAN_API_KEY" in (response.error or "")
