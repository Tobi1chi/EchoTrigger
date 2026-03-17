from __future__ import annotations

from dataclasses import replace

from hub.extractor import AudioExtractor
from hub.jobs import JobNotFoundError, JobQueueFullError, SttJobManager
from hub.models import AudioQueryRequest, AudioQueryResponse, NodeState, SttJobStatus
from hub.registry import NodeRegistry


class HubServiceError(RuntimeError):
    pass


class UnknownNodeError(HubServiceError):
    pass


class InvalidQueryError(HubServiceError):
    pass


class SttQueueUnavailableError(HubServiceError):
    pass


class UnknownJobError(HubServiceError):
    pass


class HubServices:
    def __init__(
        self,
        *,
        extractor: AudioExtractor,
        registry: NodeRegistry,
        jobs: SttJobManager,
        max_query_seconds: int,
    ) -> None:
        self._extractor = extractor
        self._registry = registry
        self._jobs = jobs
        self._max_query_seconds = max_query_seconds

    def list_nodes(self) -> list[NodeState]:
        return self._registry.list_nodes()

    def query_audio(
        self,
        *,
        node_uuid: str,
        start_time: float,
        end_time: float,
        modality: str = "audio",
    ) -> AudioQueryResponse:
        request, node = self._resolve_query(
            node_uuid=node_uuid,
            start_time=start_time,
            end_time=end_time,
            modality=modality,
        )
        return self._extractor.extract_audio(
            node_uuid=request.node_uuid,
            node_id=node.node_id,
            start_time=request.start_time,
            end_time=request.end_time,
        )

    def submit_stt_query(
        self,
        *,
        node_uuid: str,
        start_time: float,
        end_time: float,
        modality: str = "audio",
    ) -> SttJobStatus:
        request, node = self._resolve_query(
            node_uuid=node_uuid,
            start_time=start_time,
            end_time=end_time,
            modality=modality,
        )
        audio_response = self._extractor.extract_audio(
            node_uuid=request.node_uuid,
            node_id=node.node_id,
            start_time=request.start_time,
            end_time=request.end_time,
        )
        try:
            return self._jobs.submit(request, node_id=node.node_id, audio_path=audio_response.audio_path)
        except JobQueueFullError as exc:
            raise SttQueueUnavailableError(str(exc)) from exc

    def get_stt_job(self, job_id: str) -> SttJobStatus:
        cleaned = job_id.strip()
        if not cleaned:
            raise InvalidQueryError("missing job_id")
        try:
            return self._jobs.get(cleaned)
        except JobNotFoundError as exc:
            raise UnknownJobError(cleaned) from exc

    def _resolve_query(
        self,
        *,
        node_uuid: str,
        start_time: float,
        end_time: float,
        modality: str,
    ) -> tuple[AudioQueryRequest, NodeState]:
        request = self._build_query_request(
            node_uuid=node_uuid,
            start_time=start_time,
            end_time=end_time,
            modality=modality,
        )
        node = self._registry.get(request.node_uuid)
        if node is None:
            raise UnknownNodeError("unknown node_uuid")
        return request, replace(node)

    def _build_query_request(
        self,
        *,
        node_uuid: str,
        start_time: float,
        end_time: float,
        modality: str,
    ) -> AudioQueryRequest:
        try:
            request = AudioQueryRequest(
                node_uuid=str(node_uuid),
                start_time=float(start_time),
                end_time=float(end_time),
                modality=str(modality or "audio"),
            )
        except (TypeError, ValueError) as exc:
            raise InvalidQueryError("invalid query values") from exc

        if request.end_time <= request.start_time:
            raise InvalidQueryError("end_time must be greater than start_time")
        if request.end_time - request.start_time > self._max_query_seconds:
            raise InvalidQueryError(f"query window exceeds {self._max_query_seconds} seconds")
        if request.modality != "audio":
            raise InvalidQueryError("only audio modality is supported")
        return request
