from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from hub.config import HubConfig
from hub.models import NodeState
from hub.registry import NodeRegistry

PUBLISH_INTERVAL_SECONDS = 5.0
RECONCILE_TIMEOUT_SECONDS = 1.0
RECONCILE_QUIET_PERIOD_SECONDS = 0.1


class MqttClientProtocol(Protocol):
    def username_pw_set(self, username: str | None, password: str | None = None) -> None: ...
    def will_set(self, topic: str, payload: str | None = None, qos: int = 0, retain: bool = False) -> None: ...
    def connect(self, host: str, port: int, keepalive: int = 60) -> int: ...
    def loop_start(self) -> None: ...
    def loop_stop(self) -> None: ...
    def disconnect(self) -> None: ...
    def subscribe(self, topic: str, qos: int = 0): ...
    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False): ...


@dataclass(frozen=True)
class HaMqttBridgeConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    client_id: str
    discovery_prefix: str
    topic_prefix: str
    node_offline_seconds: int

    @property
    def enabled(self) -> bool:
        return bool(self.host)

    @classmethod
    def from_hub_config(cls, config: HubConfig) -> HaMqttBridgeConfig:
        return cls(
            host=config.mqtt_host,
            port=config.mqtt_port,
            username=config.mqtt_username,
            password=config.mqtt_password,
            client_id=config.mqtt_client_id,
            discovery_prefix=config.ha_discovery_prefix.strip("/") or "homeassistant",
            topic_prefix=config.mqtt_topic_prefix.strip("/") or "mic_hub",
            node_offline_seconds=max(config.node_offline_seconds, 1),
        )


class HaMqttBridge:
    def __init__(
        self,
        *,
        config: HaMqttBridgeConfig,
        registry: NodeRegistry,
        mqtt_client: MqttClientProtocol | None = None,
        now_fn=None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._client = mqtt_client
        self._now_fn = now_fn or time.time
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logger = logging.getLogger("pc_hub.ha_mqtt")
        self._known_nodes: dict[str, str] = {}
        self._published_node_online_topics: set[str] = set()
        self._broker_node_online_topics: set[str] = set()
        self._hub_discovery_published = False
        self._running = False
        self._reconcile_lock = threading.Lock()
        self._last_retained_message_at: float | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if not self._config.enabled:
            self._logger.info("Home Assistant MQTT bridge disabled")
            return
        self._stop_event.clear()
        self._broker_node_online_topics.clear()
        self._published_node_online_topics.clear()
        self._last_retained_message_at = None
        self._running = True
        try:
            if self._client is None:
                self._client = self._build_default_client()
            self._client.username_pw_set(self._config.username, self._config.password)
            self._client.will_set(self._hub_availability_topic, payload="offline", qos=1, retain=True)
            self._client.connect(self._config.host, self._config.port, keepalive=30)
            self._register_callbacks()
            self._client.loop_start()
            self._subscribe_reconcile_topics()
            self._await_retained_reconcile_window()
            self._publish_initial_state()
            self._thread = threading.Thread(target=self._run, name="pc_hub_ha_mqtt", daemon=True)
            self._thread.start()
        except Exception:
            self._running = False
            self._cleanup_client()
            raise

    def stop(self) -> None:
        if not self._config.enabled or self._client is None:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._running:
            try:
                self._publish(self._hub_availability_topic, "offline", retain=True)
            except Exception:
                self._logger.warning("Failed to publish offline availability during HA MQTT bridge shutdown", exc_info=True)
        self._cleanup_client()
        self._running = False

    @property
    def _hub_device(self) -> dict[str, object]:
        return {
            "identifiers": [f"pc_hub:{self._config.client_id}"],
            "name": "PC Audio Hub",
            "manufacturer": "Custom",
            "model": "PC Audio Hub",
            "sw_version": "0.1.0",
        }

    @property
    def _hub_availability_topic(self) -> str:
        return f"{self._config.topic_prefix}/status/availability"

    def _run(self) -> None:
        while not self._stop_event.wait(PUBLISH_INTERVAL_SECONDS):
            try:
                self._publish_state()
            except Exception:
                self._logger.exception("Disabling Home Assistant MQTT bridge after publish failure")
                self._stop_event.set()
                self._cleanup_client()
                self._running = False
                return

    def _publish_initial_state(self) -> None:
        self._publish_hub_discovery_once()
        self._publish_state()
        self._reconcile_broker_topics()

    def _publish_state(self) -> None:
        self._publish(self._hub_availability_topic, "online", retain=True)
        nodes = self._registry.list_nodes()
        self._publish_hub_state(nodes)
        self._publish_nodes(nodes)
        self._publish_missing_node_online_offline(nodes)

    def _publish_hub_discovery_once(self) -> None:
        if self._hub_discovery_published:
            return
        self._publish_discovery(
            "binary_sensor",
            "hub_online",
            {
                "name": "Hub Online",
                "unique_id": f"{self._config.client_id}_hub_online",
                "device": self._hub_device,
                "state_topic": self._hub_availability_topic,
                "payload_on": "online",
                "payload_off": "offline",
                "availability_topic": self._hub_availability_topic,
            },
        )
        for key, name, icon in (
            ("visible_nodes", "Visible Nodes", "mdi:access-point-network"),
            ("online_nodes", "Online Nodes", "mdi:lan-connect"),
        ):
            self._publish_discovery(
                "sensor",
                key,
                {
                    "name": name,
                    "unique_id": f"{self._config.client_id}_{key}",
                    "device": self._hub_device,
                    "state_topic": f"{self._config.topic_prefix}/status/{key}",
                    "availability_topic": self._hub_availability_topic,
                    "icon": icon,
                },
            )
        self._publish_discovery(
            "sensor",
            "last_publish_time",
            {
                "name": "Last Publish Time",
                "unique_id": f"{self._config.client_id}_last_publish_time",
                "device": self._hub_device,
                "state_topic": f"{self._config.topic_prefix}/status/last_publish_time",
                "availability_topic": self._hub_availability_topic,
                "device_class": "timestamp",
                "icon": "mdi:clock-outline",
            },
        )
        self._hub_discovery_published = True

    def _publish_hub_state(self, nodes: list[NodeState]) -> None:
        now = self._now_fn()
        online_nodes = sum(1 for node in nodes if self._is_node_online(node, now))
        self._publish(f"{self._config.topic_prefix}/status/visible_nodes", str(len(nodes)), retain=True)
        self._publish(f"{self._config.topic_prefix}/status/online_nodes", str(online_nodes), retain=True)
        self._publish(
            f"{self._config.topic_prefix}/status/last_publish_time",
            _iso_timestamp(now),
            retain=True,
        )

    def _publish_nodes(self, nodes: list[NodeState]) -> None:
        now = self._now_fn()
        for node in nodes:
            previous_node_id = self._known_nodes.get(node.node_uuid)
            if previous_node_id != node.node_id:
                self._publish_node_discovery(node)
                self._known_nodes[node.node_uuid] = node.node_id
            self._publish_node_state(node, now)

    def _publish_missing_node_online_offline(self, nodes: list[NodeState]) -> None:
        current_topics = {self._node_online_topic(node.node_uuid) for node in nodes}
        stale_topics = self._published_node_online_topics - current_topics
        for topic in stale_topics:
            self._publish(topic, "offline", retain=True)

    def _publish_node_discovery(self, node: NodeState) -> None:
        safe_uuid = _slugify(node.node_uuid)
        node_prefix = f"{self._config.topic_prefix}/nodes/{node.node_uuid}"
        base_name = f"{node.node_id} ({node.node_uuid})"
        availability_topic = self._hub_availability_topic
        node_online_topic = f"{node_prefix}/online"

        self._publish_discovery(
            "binary_sensor",
            f"{safe_uuid}_online",
            {
                "name": f"{base_name} Online",
                "unique_id": f"{self._config.client_id}_{safe_uuid}_online",
                "device": self._hub_device,
                "state_topic": f"{node_prefix}/online",
                "payload_on": "online",
                "payload_off": "offline",
                "availability_topic": availability_topic,
            },
        )
        self._publish_discovery(
            "sensor",
            f"{safe_uuid}_node_id",
            {
                "name": f"{base_name} Node ID",
                "unique_id": f"{self._config.client_id}_{safe_uuid}_node_id",
                "device": self._hub_device,
                "state_topic": f"{node_prefix}/node_id",
                "availability_topic": availability_topic,
                "icon": "mdi:identifier",
            },
        )
        self._publish_discovery(
            "sensor",
            f"{safe_uuid}_last_seen",
            {
                "name": f"{base_name} Last Seen",
                "unique_id": f"{self._config.client_id}_{safe_uuid}_last_seen",
                "device": self._hub_device,
                "state_topic": f"{node_prefix}/last_seen",
                "availability_topic": availability_topic,
                "device_class": "timestamp",
            },
        )
        for metric in ("packets_received", "packets_missing", "packets_out_of_order"):
            self._publish_discovery(
                "sensor",
                f"{safe_uuid}_{metric}",
                {
                    "name": f"{base_name} {metric.replace('_', ' ').title()}",
                    "unique_id": f"{self._config.client_id}_{safe_uuid}_{metric}",
                    "device": self._hub_device,
                    "state_topic": f"{node_prefix}/{metric}",
                    "availability_topic": availability_topic,
                    "icon": "mdi:counter",
                },
            )
        self._publish_discovery(
            "button",
            f"{safe_uuid}_streaming_on",
            {
                "name": f"{base_name} Start Streaming",
                "unique_id": f"{self._config.client_id}_{safe_uuid}_streaming_on",
                "device": self._hub_device,
                "command_topic": f"mic/{node.node_uuid}/cmd/streaming/set",
                "payload_press": "ON",
                "availability": [
                    {"topic": availability_topic, "payload_available": "online", "payload_not_available": "offline"},
                    {"topic": node_online_topic, "payload_available": "online", "payload_not_available": "offline"},
                ],
                "availability_mode": "all",
                "icon": "mdi:microphone",
            },
        )
        self._publish_discovery(
            "button",
            f"{safe_uuid}_streaming_off",
            {
                "name": f"{base_name} Stop Streaming",
                "unique_id": f"{self._config.client_id}_{safe_uuid}_streaming_off",
                "device": self._hub_device,
                "command_topic": f"mic/{node.node_uuid}/cmd/streaming/set",
                "payload_press": "OFF",
                "availability": [
                    {"topic": availability_topic, "payload_available": "online", "payload_not_available": "offline"},
                    {"topic": node_online_topic, "payload_available": "online", "payload_not_available": "offline"},
                ],
                "availability_mode": "all",
                "icon": "mdi:microphone-off",
            },
        )
        self._publish_discovery(
            "button",
            f"{safe_uuid}_restart",
            {
                "name": f"{base_name} Restart",
                "unique_id": f"{self._config.client_id}_{safe_uuid}_restart",
                "device": self._hub_device,
                "command_topic": f"mic/{node.node_uuid}/cmd/restart",
                "payload_press": "restart",
                "availability": [
                    {"topic": availability_topic, "payload_available": "online", "payload_not_available": "offline"},
                    {"topic": node_online_topic, "payload_available": "online", "payload_not_available": "offline"},
                ],
                "availability_mode": "all",
                "icon": "mdi:restart",
            },
        )

    def _publish_node_state(self, node: NodeState, now: float) -> None:
        node_prefix = f"{self._config.topic_prefix}/nodes/{node.node_uuid}"
        online_topic = self._node_online_topic(node.node_uuid)
        self._publish(online_topic, "online" if self._is_node_online(node, now) else "offline", retain=True)
        self._published_node_online_topics.add(online_topic)
        self._publish(node_prefix + "/node_id", node.node_id, retain=True)
        self._publish(node_prefix + "/last_seen", _iso_timestamp(node.last_seen), retain=True)
        self._publish(node_prefix + "/packets_received", str(node.packets_received), retain=True)
        self._publish(node_prefix + "/packets_missing", str(node.packets_missing), retain=True)
        self._publish(node_prefix + "/packets_out_of_order", str(node.packets_out_of_order), retain=True)

    def _publish_discovery(self, component: str, object_id: str, payload: dict[str, object]) -> None:
        topic = f"{self._config.discovery_prefix}/{component}/{self._config.client_id}/{object_id}/config"
        self._publish(topic, json.dumps(payload, ensure_ascii=True), retain=True)

    def _publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        assert self._client is not None
        self._client.publish(topic, payload, qos=1, retain=retain)

    def _is_node_online(self, node: NodeState, now: float | None = None) -> bool:
        current = self._now_fn() if now is None else now
        return current - node.last_seen <= self._config.node_offline_seconds

    def _build_default_client(self) -> MqttClientProtocol:
        try:
            import paho.mqtt.client as mqtt
        except ModuleNotFoundError as exc:
            raise RuntimeError("paho-mqtt is required for Home Assistant MQTT bridge") from exc
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self._config.client_id)

    def _cleanup_client(self) -> None:
        if self._client is None:
            return
        try:
            self._client.loop_stop()
        except Exception:
            pass
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._thread = None
        self._last_retained_message_at = None

    def _node_online_topic(self, node_uuid: str) -> str:
        return f"{self._config.topic_prefix}/nodes/{node_uuid}/online"

    def _node_online_subscription(self) -> str:
        return f"{self._config.topic_prefix}/nodes/+/online"

    def _register_callbacks(self) -> None:
        assert self._client is not None
        try:
            setattr(self._client, "on_message", self._on_message)
        except Exception:
            self._logger.debug("MQTT client does not support on_message attribute assignment", exc_info=True)

    def _subscribe_reconcile_topics(self) -> None:
        assert self._client is not None
        result = self._client.subscribe(self._node_online_subscription(), qos=1)
        if isinstance(result, tuple) and result:
            if int(result[0]) != 0:
                raise RuntimeError(f"failed to subscribe to MQTT reconcile topic: rc={result[0]}")

    def _await_retained_reconcile_window(self) -> None:
        deadline = self._now_fn() + RECONCILE_TIMEOUT_SECONDS
        while self._now_fn() < deadline:
            with self._reconcile_lock:
                last_seen = self._last_retained_message_at
            if last_seen is None:
                time.sleep(RECONCILE_QUIET_PERIOD_SECONDS)
                return
            if self._now_fn() - last_seen >= RECONCILE_QUIET_PERIOD_SECONDS:
                return
            time.sleep(0.01)
        raise RuntimeError("timed out while waiting for retained MQTT reconcile messages")

    def _on_message(self, _client: object, _userdata: object, message: Any) -> None:
        topic = getattr(message, "topic", "")
        retain = bool(getattr(message, "retain", False))
        if not retain or not isinstance(topic, str):
            return
        if not self._matches_node_online_topic(topic):
            return
        with self._reconcile_lock:
            self._broker_node_online_topics.add(topic)
            self._last_retained_message_at = self._now_fn()

    def _reconcile_broker_topics(self) -> None:
        current_topics = {self._node_online_topic(node.node_uuid) for node in self._registry.list_nodes()}
        with self._reconcile_lock:
            stale_topics = self._broker_node_online_topics - current_topics
        for topic in stale_topics:
            self._publish(topic, "offline", retain=True)

    def _matches_node_online_topic(self, topic: str) -> bool:
        prefix = f"{self._config.topic_prefix}/nodes/"
        return topic.startswith(prefix) and topic.endswith("/online")


def _iso_timestamp(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def _slugify(value: str) -> str:
    chars = [ch if ch.isalnum() else "_" for ch in value.lower()]
    return "".join(chars)
