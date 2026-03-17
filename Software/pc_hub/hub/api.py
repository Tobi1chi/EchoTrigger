from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hub.extractor import AudioExtractor
from hub.models import AudioQueryRequest, SttJobRequest
from hub.registry import NodeRegistry
from shared.timebase import PC_RECEIVE_TIMEBASE


class HubRequestHandler(BaseHTTPRequestHandler):
    extractor: AudioExtractor
    registry: NodeRegistry
    worker_url: str
    logger = logging.getLogger("pc_hub.api")

    def do_GET(self) -> None:  # noqa: N802
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

        stt_request = SttJobRequest(
            job_id=str(uuid.uuid4()),
            audio_path=audio_response.audio_path,
            node_uuid=request.node_uuid,
            node_id=node.node_id,
            start_time=request.start_time,
            end_time=request.end_time,
        )
        try:
            worker_response = _call_worker(self.worker_url, stt_request)
        except RuntimeError as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
            return

        payload = {
            "node_uuid": request.node_uuid,
            "node_id": node.node_id,
            "audio_path": audio_response.audio_path,
            "timebase": PC_RECEIVE_TIMEBASE,
            **worker_response,
        }
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
    worker_url: str,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredHubHandler",
        (HubRequestHandler,),
        {"extractor": extractor, "registry": registry, "worker_url": worker_url},
    )
    return ThreadingHTTPServer((host, port), handler)


def _call_worker(worker_url: str, request: SttJobRequest) -> dict[str, object]:
    payload = json.dumps(
        {
            "job_id": request.job_id,
            "audio_path": request.audio_path,
            "node_uuid": request.node_uuid,
            "node_id": request.node_id,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "modality": request.modality,
        }
    ).encode("utf-8")
    http_request = urllib.request.Request(
        worker_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"worker request failed: {exc}") from exc
    return data
