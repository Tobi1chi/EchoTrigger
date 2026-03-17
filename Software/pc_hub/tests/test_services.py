from __future__ import annotations

from dataclasses import replace

import pytest

from hub.models import AudioQueryResponse, NodeState, SttJobStatus
from hub.services import HubServices, InvalidQueryError, UnknownJobError, UnknownNodeError


class _StubExtractor:
    def extract_audio(self, *, node_uuid: str, node_id: str, start_time: float, end_time: float) -> AudioQueryResponse:
        return AudioQueryResponse(
            node_uuid=node_uuid,
            node_id=node_id,
            audio_path="/tmp/test.wav",
            sample_rate=16000,
            duration_seconds=end_time - start_time,
            start_time=start_time,
            end_time=end_time,
        )


class _StubRegistry:
    def __init__(self) -> None:
        self.node = NodeState(
            node_uuid="node-1",
            node_id="kitchen",
            last_seen=1.0,
            last_seq=10,
            packets_received=5,
        )

    def get(self, node_uuid: str) -> NodeState | None:
        if node_uuid != self.node.node_uuid:
            return None
        return replace(self.node)

    def list_nodes(self) -> list[NodeState]:
        return [replace(self.node)]


class _StubJobs:
    def __init__(self) -> None:
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

    def submit(self, request, *, node_id: str, audio_path: str) -> SttJobStatus:
        assert request.node_uuid == "node-1"
        assert node_id == "kitchen"
        assert audio_path == "/tmp/test.wav"
        return replace(self.job)

    def get(self, job_id: str) -> SttJobStatus:
        if job_id != self.job.job_id:
            from hub.jobs import JobNotFoundError

            raise JobNotFoundError(job_id)
        return replace(self.job)


@pytest.fixture
def services() -> HubServices:
    return HubServices(
        extractor=_StubExtractor(),
        registry=_StubRegistry(),
        jobs=_StubJobs(),
        max_query_seconds=120,
    )


def test_list_nodes_returns_registry_state(services: HubServices) -> None:
    nodes = services.list_nodes()

    assert [node.node_uuid for node in nodes] == ["node-1"]


def test_submit_stt_query_rejects_unknown_node(services: HubServices) -> None:
    with pytest.raises(UnknownNodeError):
        services.submit_stt_query(node_uuid="missing", start_time=10.0, end_time=11.0)


def test_submit_stt_query_rejects_invalid_window(services: HubServices) -> None:
    with pytest.raises(InvalidQueryError):
        services.submit_stt_query(node_uuid="node-1", start_time=11.0, end_time=10.0)


def test_get_stt_job_rejects_unknown_job(services: HubServices) -> None:
    with pytest.raises(UnknownJobError):
        services.get_stt_job("missing")
