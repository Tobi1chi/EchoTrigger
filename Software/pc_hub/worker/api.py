from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from worker.backends.base import SttBackend


class WorkerRequestHandler(BaseHTTPRequestHandler):
    adapter: SttBackend
    logger = logging.getLogger("pc_hub.worker.api")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/transcribe":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        body = self._read_json()
        if body is None:
            return

        required = ("job_id", "audio_path", "node_uuid", "node_id", "start_time", "end_time")
        missing = [key for key in required if key not in body]
        if missing:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"missing fields: {', '.join(missing)}"})
            return

        response = self.adapter.transcribe(job_id=body["job_id"], audio_path=body["audio_path"])
        self._send_json(HTTPStatus.OK, response.to_dict())

    def log_message(self, format: str, *args: object) -> None:
        self.logger.info("%s - %s", self.client_address[0], format % args)

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


def build_server(host: str, port: int, adapter: SttBackend) -> ThreadingHTTPServer:
    handler = type("ConfiguredWorkerHandler", (WorkerRequestHandler,), {"adapter": adapter})
    return ThreadingHTTPServer((host, port), handler)
