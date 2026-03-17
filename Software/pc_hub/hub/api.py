from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hub.extractor import AudioExtractor
from hub.jobs import JobNotFoundError, JobQueueFullError, SttJobManager
from hub.models import AudioQueryRequest
from hub.registry import NodeRegistry
from shared.timebase import PC_RECEIVE_TIMEBASE


class HubRequestHandler(BaseHTTPRequestHandler):
    extractor: AudioExtractor
    registry: NodeRegistry
    jobs: SttJobManager
    max_query_seconds: int
    logger = logging.getLogger("pc_hub.api")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/jobs/"):
            self._handle_job_get()
            return
        if self.path != "/nodes":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        nodes = [node.to_dict() for node in self.registry.list_nodes()]
        self._send_json(HTTPStatus.OK, {"timebase": PC_RECEIVE_TIMEBASE, "nodes": nodes})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/query/audio":
            self._handle_audio_query()
            return
        if self.path == "/query/stt":
            self._handle_stt_query()
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        self.logger.info("%s - %s", self.client_address[0], format % args)

    def _handle_audio_query(self) -> None:
        request = self._parse_query_request()
        if request is None:
            return

        node = self.registry.get(request.node_uuid)
        if node is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown node_uuid"})
            return

        try:
            response = self.extractor.extract_audio(
                node_uuid=request.node_uuid,
                node_id=node.node_id,
                start_time=request.start_time,
                end_time=request.end_time,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
            return

        payload = response.to_dict()
        payload["timebase"] = PC_RECEIVE_TIMEBASE
        self._send_json(HTTPStatus.OK, payload)

    def _handle_stt_query(self) -> None:
        request = self._parse_query_request()
        if request is None:
            return

        node = self.registry.get(request.node_uuid)
        if node is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown node_uuid"})
            return

        try:
            audio_response = self.extractor.extract_audio(
                node_uuid=request.node_uuid,
                node_id=node.node_id,
                start_time=request.start_time,
                end_time=request.end_time,
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
            return

        try:
            job = self.jobs.submit(request, node_id=node.node_id)
        except JobQueueFullError as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
            return

        payload = {
            "timebase": PC_RECEIVE_TIMEBASE,
            **job.to_dict(),
        }
        self._send_json(HTTPStatus.ACCEPTED, payload)

    def _handle_job_get(self) -> None:
        job_id = self.path.removeprefix("/jobs/").strip()
        if not job_id:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "missing job_id"})
            return

        try:
            job = self.jobs.get(job_id)
        except JobNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown job_id", "timebase": PC_RECEIVE_TIMEBASE})
            return
        payload = job.to_dict()
        payload["timebase"] = PC_RECEIVE_TIMEBASE
        self._send_json(HTTPStatus.OK, payload)

    def _parse_query_request(self) -> AudioQueryRequest | None:
        body = self._read_json()
        if body is None:
            return None

        required = ("node_uuid", "start_time", "end_time")
        missing = [key for key in required if key not in body]
        if missing:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"missing fields: {', '.join(missing)}"})
            return None

        try:
            request = AudioQueryRequest(
                node_uuid=str(body["node_uuid"]),
                start_time=float(body["start_time"]),
                end_time=float(body["end_time"]),
                modality=str(body.get("modality", "audio")),
            )
        except (TypeError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid query values"})
            return None

        if request.end_time <= request.start_time:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "end_time must be greater than start_time"})
            return None
        if request.end_time - request.start_time > self.max_query_seconds:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"query window exceeds {self.max_query_seconds} seconds"},
            )
            return None
        if request.modality != "audio":
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "only audio modality is supported"})
            return None
        return request

    def _read_json(self) -> dict[str, object] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid content-length"})
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid json"})
            return None

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def build_server(
    host: str,
    port: int,
    *,
    extractor: AudioExtractor,
    registry: NodeRegistry,
    jobs: SttJobManager,
    max_query_seconds: int,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredHubHandler",
        (HubRequestHandler,),
        {
            "extractor": extractor,
            "registry": registry,
            "jobs": jobs,
            "max_query_seconds": max_query_seconds,
        },
    )
    return ThreadingHTTPServer((host, port), handler)
