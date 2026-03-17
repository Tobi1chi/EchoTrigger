from __future__ import annotations

import threading

from hub.models import AudioFrame, NodeState


class NodeRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, NodeState] = {}

    def register_frame(self, frame: AudioFrame) -> NodeState:
        with self._lock:
            state = self._states.get(frame.node_uuid)
            if state is None:
                state = NodeState(
                    node_uuid=frame.node_uuid,
                    node_id=frame.node_id,
                    last_seen=frame.arrival_time,
                    last_seq=frame.seq,
                    packets_received=1,
                )
                self._states[frame.node_uuid] = state
                return state

            if frame.seq <= state.last_seq:
                state.packets_out_of_order += 1
            elif frame.seq > state.last_seq + 1:
                state.packets_missing += frame.seq - state.last_seq - 1

            state.node_id = frame.node_id
            state.last_seen = frame.arrival_time
            state.last_seq = max(state.last_seq, frame.seq)
            state.packets_received += 1
            return state

    def get(self, node_uuid: str) -> NodeState | None:
        with self._lock:
            state = self._states.get(node_uuid)
            if state is None:
                return None
            return NodeState(**state.to_dict())

    def list_nodes(self) -> list[NodeState]:
        with self._lock:
            return [NodeState(**state.to_dict()) for state in self._states.values()]
