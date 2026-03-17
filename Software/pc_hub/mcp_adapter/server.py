from __future__ import annotations

from dataclasses import replace
from typing import Any

from mcp.server.fastmcp import FastMCP

from hub.config import HubConfig
from hub.services import HubServices, InvalidQueryError, SttQueueUnavailableError, UnknownJobError, UnknownNodeError
from shared.timebase import PC_RECEIVE_TIMEBASE


class PcHubMcpAdapter:
    def __init__(self, services: HubServices) -> None:
        self._services = services

    def list_nodes(self) -> dict[str, Any]:
        return {
            "timebase": PC_RECEIVE_TIMEBASE,
            "nodes": [node.to_dict() for node in self._services.list_nodes()],
        }

    def submit_stt_job(self, node_uuid: str, start_time: float, end_time: float) -> dict[str, Any]:
        try:
            job = self._services.submit_stt_query(
                node_uuid=node_uuid,
                start_time=start_time,
                end_time=end_time,
            )
        except (UnknownNodeError, InvalidQueryError, SttQueueUnavailableError) as exc:
            return {"timebase": PC_RECEIVE_TIMEBASE, "error": str(exc)}
        except ValueError as exc:
            return {"timebase": PC_RECEIVE_TIMEBASE, "error": str(exc)}
        return {"timebase": PC_RECEIVE_TIMEBASE, **replace(job).to_dict()}

    def get_stt_job(self, job_id: str) -> dict[str, Any]:
        try:
            job = self._services.get_stt_job(job_id)
        except UnknownJobError as exc:
            return {"timebase": PC_RECEIVE_TIMEBASE, "error": f"unknown job_id: {exc}"}
        except InvalidQueryError as exc:
            return {"timebase": PC_RECEIVE_TIMEBASE, "error": str(exc)}
        return {"timebase": PC_RECEIVE_TIMEBASE, **replace(job).to_dict()}


def build_mcp_server(config: HubConfig, services: HubServices) -> FastMCP:
    adapter = PcHubMcpAdapter(services)
    server = FastMCP(
        name="pc-audio-hub",
        instructions=(
            "Use this server to discover microphone nodes, submit asynchronous STT jobs over "
            "pc_receive_time windows, and poll job status."
        ),
        host=config.mcp_bind_host,
        port=config.mcp_port,
        streamable_http_path=config.mcp_path,
    )

    @server.tool(
        description="List microphone nodes currently visible to the PC audio hub. Timebase is pc_receive_time."
    )
    def list_nodes() -> dict[str, Any]:
        return adapter.list_nodes()

    @server.tool(
        description=(
            "Submit an asynchronous STT job for one node over a pc_receive_time window. "
            "Returns a job_id that must be polled with get_stt_job."
        )
    )
    def submit_stt_job(node_uuid: str, start_time: float, end_time: float) -> dict[str, Any]:
        return adapter.submit_stt_job(node_uuid, start_time, end_time)

    @server.tool(
        description=(
            "Get the current status for a previously submitted STT job. "
            "Status may be queued, running, succeeded, failed, or expired."
        )
    )
    def get_stt_job(job_id: str) -> dict[str, Any]:
        return adapter.get_stt_job(job_id)

    return server
