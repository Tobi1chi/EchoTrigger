from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from hub.config import HubConfig
from hub.models import NodeState, SttJobStatus
from mcp_adapter.server import PcHubMcpAdapter, build_mcp_server


class _StubServices:
    def __init__(self) -> None:
        self.node = NodeState(
            node_uuid="node-1",
            node_id="kitchen",
            last_seen=1.0,
            last_seq=10,
            packets_received=5,
        )
        self.job = SttJobStatus(
            job_id="job-1",
            status="queued",
            node_uuid="node-1",
            node_id="kitchen",
            start_time=10.0,
            end_time=11.0,
            created_at=1.0,
            updated_at=1.0,
            audio_path="/tmp/test.wav",
        )

    def list_nodes(self) -> list[NodeState]:
        return [replace(self.node)]

    def submit_stt_query(self, *, node_uuid: str, start_time: float, end_time: float, modality: str = "audio") -> SttJobStatus:
        assert node_uuid == "node-1"
        assert start_time == 10.0
        assert end_time == 11.0
        assert modality == "audio"
        return replace(self.job)

    def get_stt_job(self, job_id: str) -> SttJobStatus:
        assert job_id == "job-1"
        return replace(self.job)


def _config() -> HubConfig:
    return HubConfig(
        bind_host="127.0.0.1",
        http_port=8765,
        legacy_http_enabled=False,
        udp_host="0.0.0.0",
        udp_port=4000,
        ring_minutes=10,
        clip_dir=Path("/tmp"),
        worker_url="http://127.0.0.1:8766/transcribe",
        clip_ttl_seconds=900,
        max_query_seconds=120,
        stt_job_queue_size=16,
        stt_job_ttl_seconds=900,
        mcp_bind_host="127.0.0.1",
        mcp_port=8767,
        mcp_path="/mcp",
        mqtt_host="",
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password=None,
        mqtt_client_id="pc-audio-hub",
        ha_discovery_prefix="homeassistant",
        mqtt_topic_prefix="mic_hub",
        node_offline_seconds=30,
    )


def test_mcp_adapter_returns_expected_tool_payloads() -> None:
    adapter = PcHubMcpAdapter(_StubServices())

    nodes = adapter.list_nodes()
    job = adapter.submit_stt_job("node-1", 10.0, 11.0)
    status = adapter.get_stt_job("job-1")

    assert nodes["nodes"][0]["node_uuid"] == "node-1"
    assert job["job_id"] == "job-1"
    assert status["status"] == "queued"


def test_build_mcp_server_registers_expected_tools() -> None:
    server = build_mcp_server(_config(), _StubServices())
    tool_names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert tool_names == {"list_nodes", "submit_stt_job", "get_stt_job"}
