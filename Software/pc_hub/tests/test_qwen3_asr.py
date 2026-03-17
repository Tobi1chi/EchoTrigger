from __future__ import annotations

from worker.backends import qwen3_asr


def test_default_device_map_uses_auto_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(qwen3_asr.platform, "system", lambda: "Windows")
    monkeypatch.setattr(qwen3_asr.platform, "machine", lambda: "AMD64")

    assert qwen3_asr.default_device_map() == "auto"


def test_candidate_device_maps_try_cuda_then_cpu_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(qwen3_asr.platform, "system", lambda: "Windows")
    monkeypatch.setattr(qwen3_asr.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(qwen3_asr.torch.cuda, "is_available", lambda: True)

    assert qwen3_asr._candidate_device_maps("auto") == ("cuda", "cpu")


def test_candidate_device_maps_fall_back_to_cpu_without_cuda(monkeypatch) -> None:
    monkeypatch.setattr(qwen3_asr.platform, "system", lambda: "Windows")
    monkeypatch.setattr(qwen3_asr.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(qwen3_asr.torch.cuda, "is_available", lambda: False)

    assert qwen3_asr._candidate_device_maps("auto") == ("cpu",)


def test_candidate_device_maps_preserve_explicit_override(monkeypatch) -> None:
    monkeypatch.setattr(qwen3_asr.platform, "system", lambda: "Windows")
    monkeypatch.setattr(qwen3_asr.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(qwen3_asr.torch.cuda, "is_available", lambda: True)

    assert qwen3_asr._candidate_device_maps("cpu") == ("cpu",)
