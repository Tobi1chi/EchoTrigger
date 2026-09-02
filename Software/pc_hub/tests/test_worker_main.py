from __future__ import annotations

import pytest

import worker.main
from worker.backends.bailian_qwen_asr import BailianQwenAsrBackend
from worker.backends.qwen3_asr import Qwen3AsrBackend


def test_build_backend_defaults_to_bailian(monkeypatch) -> None:
    monkeypatch.delenv("PC_HUB_ASR_PROVIDER", raising=False)
    monkeypatch.setenv("PC_HUB_BAILIAN_API_KEY", "test-key")

    backend = worker.main.build_backend()

    assert isinstance(backend, BailianQwenAsrBackend)


def test_bailian_base_url_can_use_workspace_domain(monkeypatch) -> None:
    monkeypatch.delenv("PC_HUB_BAILIAN_BASE_URL", raising=False)
    monkeypatch.setenv("PC_HUB_BAILIAN_WORKSPACE_ID", "ws-test")
    monkeypatch.setenv("PC_HUB_BAILIAN_REGION", "ap-southeast-1")

    assert (
        worker.main._bailian_base_url()
        == "https://ws-test.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )


def test_build_backend_can_select_local_qwen3(monkeypatch) -> None:
    monkeypatch.setenv("PC_HUB_ASR_PROVIDER", "local-qwen3")

    backend = worker.main.build_backend()

    assert isinstance(backend, Qwen3AsrBackend)


def test_build_backend_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setenv("PC_HUB_ASR_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported PC_HUB_ASR_PROVIDER"):
        worker.main.build_backend()
