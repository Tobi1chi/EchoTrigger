from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hub.services import HubServices, InvalidQueryError, SttQueueUnavailableError, UnknownJobError, UnknownNodeError
from shared.timebase import PC_RECEIVE_TIMEBASE


class HubRequestHandler(BaseHTTPRequestHandler):
    services: HubServices
    logger = logging.getLogger("pc_hub.api")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/jobs/"):
            self._handle_job_get()
            return
        if self.path != "/nodes":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        nodes = [node.to_dict() for node in self.services.list_nodes()]
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
        body = self._read_json()
        if body is None:
            return
        if not self._validate_query_body(body):
            return

        try:
            response = self.services.query_audio(
                node_uuid=body.get("node_uuid", ""),
                start_time=body.get("start_time"),
                end_time=body.get("end_time"),
                modality=str(body.get("modality", "audio")),
            )
        except UnknownNodeError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except InvalidQueryError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
            return

        payload = response.to_dict()
        payload["timebase"] = PC_RECEIVE_TIMEBASE
        self._send_json(HTTPStatus.OK, payload)

    def _handle_stt_query(self) -> None:
        body = self._read_json()
        if body is None:
            return
        if not self._validate_query_body(body):
            return

        try:
            job = self.services.submit_stt_query(
                node_uuid=body.get("node_uuid", ""),
                start_time=body.get("start_time"),
                end_time=body.get("end_time"),
                modality=str(body.get("modality", "audio")),
            )
        except UnknownNodeError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except InvalidQueryError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except SttQueueUnavailableError as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc), "timebase": PC_RECEIVE_TIMEBASE})
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
            job = self.services.get_stt_job(job_id)
        except UnknownJobError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown job_id", "timebase": PC_RECEIVE_TIMEBASE})
            return
        payload = job.to_dict()
        payload["timebase"] = PC_RECEIVE_TIMEBASE
        self._send_json(HTTPStatus.OK, payload)

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

    def _validate_query_body(self, body: dict[str, object]) -> bool:
        required = ("node_uuid", "start_time", "end_time")
        missing = [key for key in required if key not in body]
        if missing:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"missing fields: {', '.join(missing)}"})
            return False
        return True

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("X-PC-Hub-Legacy-API", "deprecated")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def build_server(
    host: str,
    port: int,
    *,
    services: HubServices,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredHubHandler",
        (HubRequestHandler,),
        {"services": services},
    )
    return ThreadingHTTPServer((host, port), handler)
