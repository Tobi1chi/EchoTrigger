from __future__ import annotations

from types import SimpleNamespace

import hub.main
import mcp_adapter.main


class _StopMain(Exception):
    pass


class _ServerStub:
    def serve_forever(self) -> None:
        raise _StopMain()


class _LegacyServerStub:
    def serve_forever(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def server_close(self) -> None:
        return None


class _McpServerStub:
    def run(self, transport: str) -> None:
        raise _StopMain()


class _RuntimeStub:
    def __init__(self, running: bool) -> None:
        self.ha_bridge_running = running
        self.services = object()
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def _config():
    return SimpleNamespace(
        udp_host="0.0.0.0",
        udp_port=4000,
        bind_host="127.0.0.1",
        http_port=8765,
        worker_url="http://127.0.0.1:8766/transcribe",
        clip_ttl_seconds=900,
        max_query_seconds=120,
        stt_job_queue_size=16,
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_topic_prefix="mic_hub",
        legacy_http_enabled=False,
        mcp_bind_host="127.0.0.1",
        mcp_port=8767,
        mcp_path="/mcp",
    )


def test_hub_main_logs_warning_when_bridge_is_configured_but_not_running(monkeypatch, caplog) -> None:
    caplog.set_level("INFO")
    runtime = _RuntimeStub(running=False)
    monkeypatch.setattr(hub.main, "load_config", _config)
    monkeypatch.setattr(hub.main.HubRuntime, "from_config", lambda config: runtime)
    monkeypatch.setattr(hub.main, "build_server", lambda host, port, services: _ServerStub())

    try:
        hub.main.main()
    except _StopMain:
        pass

    assert "configured for 127.0.0.1:1883 but is not running" in caplog.text


def test_mcp_main_logs_enabled_only_when_bridge_is_running(monkeypatch, caplog) -> None:
    caplog.set_level("INFO")
    runtime = _RuntimeStub(running=True)
    monkeypatch.setattr(mcp_adapter.main, "load_config", _config)
    monkeypatch.setattr(mcp_adapter.main.HubRuntime, "from_config", lambda config: runtime)
    monkeypatch.setattr(mcp_adapter.main, "build_server", lambda host, port, services: _LegacyServerStub())
    monkeypatch.setattr(mcp_adapter.main, "build_mcp_server", lambda config, services: _McpServerStub())

    try:
        mcp_adapter.main.main()
    except _StopMain:
        pass

    assert "Home Assistant MQTT bridge enabled for 127.0.0.1:1883 with topic prefix mic_hub" in caplog.text
    assert "but is not running" not in caplog.text
