from __future__ import annotations

from hub.runtime import HubRuntime


class _Recorder:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FailingBridge:
    is_running = False

    def start(self) -> None:
        raise RuntimeError("bridge failed")

    def stop(self) -> None:
        pass


class _RunningBridge:
    is_running = True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_runtime_start_continues_when_ha_bridge_fails(caplog) -> None:
    receiver = _Recorder()
    jobs = _Recorder()
    runtime = HubRuntime(
        config=None,  # type: ignore[arg-type]
        registry=None,  # type: ignore[arg-type]
        ring_buffers=None,  # type: ignore[arg-type]
        storage=None,  # type: ignore[arg-type]
        extractor=None,  # type: ignore[arg-type]
        jobs=jobs,  # type: ignore[arg-type]
        receiver=receiver,  # type: ignore[arg-type]
        services=None,  # type: ignore[arg-type]
        ha_bridge=_FailingBridge(),  # type: ignore[arg-type]
    )

    runtime.start()

    assert receiver.started is True
    assert jobs.started is True
    assert runtime.ha_bridge_running is False
    assert "continuing without HA integration" in caplog.text


def test_runtime_reports_running_bridge_state() -> None:
    runtime = HubRuntime(
        config=None,  # type: ignore[arg-type]
        registry=None,  # type: ignore[arg-type]
        ring_buffers=None,  # type: ignore[arg-type]
        storage=None,  # type: ignore[arg-type]
        extractor=None,  # type: ignore[arg-type]
        jobs=_Recorder(),  # type: ignore[arg-type]
        receiver=_Recorder(),  # type: ignore[arg-type]
        services=None,  # type: ignore[arg-type]
        ha_bridge=_RunningBridge(),  # type: ignore[arg-type]
    )

    runtime.start()

    assert runtime.ha_bridge_running is True
