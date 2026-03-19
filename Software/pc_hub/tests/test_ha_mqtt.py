from __future__ import annotations

import json
import time

import hub.ha_mqtt as ha_mqtt_module
from hub.ha_mqtt import HaMqttBridge, HaMqttBridgeConfig
from hub.models import AudioFrame, NodeState
from hub.registry import NodeRegistry


class _FakeClient:
    def __init__(self) -> None:
        self.username = None
        self.password = None
        self.will = None
        self.connected = None
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False
        self.subscriptions: list[tuple[str, int]] = []
        self.published: list[tuple[str, str, int, bool]] = []
        self.on_message = None

    def username_pw_set(self, username: str | None, password: str | None = None) -> None:
        self.username = username
        self.password = password

    def will_set(self, topic: str, payload: str | None = None, qos: int = 0, retain: bool = False) -> None:
        self.will = (topic, payload, qos, retain)

    def connect(self, host: str, port: int, keepalive: int = 60) -> int:
        self.connected = (host, port, keepalive)
        return 0

    def loop_start(self) -> None:
        self.loop_started = True

    def loop_stop(self) -> None:
        self.loop_stopped = True

    def disconnect(self) -> None:
        self.disconnected = True

    def subscribe(self, topic: str, qos: int = 0):
        self.subscriptions.append((topic, qos))
        return (0, 1)

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        self.published.append((topic, payload, qos, retain))
        return None


class _FailingClient(_FakeClient):
    def connect(self, host: str, port: int, keepalive: int = 60) -> int:
        raise RuntimeError("connect failed")


class _RetainedClient(_FakeClient):
    def __init__(self, retained_topics: list[str]) -> None:
        super().__init__()
        self.retained_topics = retained_topics

    def subscribe(self, topic: str, qos: int = 0):
        result = super().subscribe(topic, qos)
        if self.on_message is not None:
            for retained_topic in self.retained_topics:
                message = type("Message", (), {"topic": retained_topic, "retain": True})()
                self.on_message(self, None, message)
        return result


class _SubscribeFailingClient(_FakeClient):
    def subscribe(self, topic: str, qos: int = 0):
        self.subscriptions.append((topic, qos))
        return (1, 1)


class _DelayedRetainedClient(_FakeClient):
    def __init__(self, retained_topics: list[str], delay_seconds: float) -> None:
        super().__init__()
        self.retained_topics = retained_topics
        self.delay_seconds = delay_seconds

    def subscribe(self, topic: str, qos: int = 0):
        result = super().subscribe(topic, qos)
        if self.on_message is not None:
            import threading

            def _emit() -> None:
                time.sleep(self.delay_seconds)
                for retained_topic in self.retained_topics:
                    message = type("Message", (), {"topic": retained_topic, "retain": True})()
                    self.on_message(self, None, message)

            threading.Thread(target=_emit, daemon=True).start()
        return result


class _NoisyRetainedClient(_FakeClient):
    def subscribe(self, topic: str, qos: int = 0):
        result = super().subscribe(topic, qos)
        if self.on_message is not None:
            import threading

            def _emit() -> None:
                for _ in range(10):
                    message = type("Message", (), {"topic": "mic_hub/nodes/esp32s3-noisy/online", "retain": True})()
                    self.on_message(self, None, message)
                    time.sleep(0.02)

            threading.Thread(target=_emit, daemon=True).start()
        return result


class _RegistryStub:
    def __init__(self, nodes: list[NodeState] | None = None) -> None:
        self.nodes = nodes or []

    def list_nodes(self) -> list[NodeState]:
        return [NodeState(**node.to_dict()) for node in self.nodes]


class _ThreadFailureBridge(HaMqttBridge):
    def _run(self) -> None:
        self._cleanup_client()
        self._running = False


def _bridge(*, now: float) -> tuple[HaMqttBridge, _FakeClient, NodeRegistry]:
    registry = NodeRegistry()
    client = _FakeClient()
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
        now_fn=lambda: now,
    )
    return bridge, client, registry


def _register_node(registry: NodeRegistry, *, last_seen: float, node_uuid: str = "esp32s3-abc", node_id: str = "kitchen") -> None:
    registry.register_frame(
        AudioFrame(
            node_uuid=node_uuid,
            node_id=node_id,
            seq=10,
            timestamp_us=123,
            sample_rate=16000,
            channels=1,
            bits_per_sample=16,
            payload_bytes=320,
            samples=b"\x00" * 320,
            arrival_time=last_seen,
        )
    )


def test_node_online_state_uses_last_seen_threshold() -> None:
    bridge, _, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=80.0)
    node = registry.list_nodes()[0]

    assert bridge._is_node_online(node, 100.0) is True
    assert bridge._is_node_online(node, 111.0) is False


def test_publish_all_emits_hub_and_node_topics() -> None:
    bridge, client, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=95.0)

    bridge._publish_initial_state()

    published = {topic: payload for topic, payload, _qos, _retain in client.published}
    assert published["mic_hub/status/visible_nodes"] == "1"
    assert published["mic_hub/status/online_nodes"] == "1"
    assert published["mic_hub/nodes/esp32s3-abc/online"] == "online"
    assert published["mic_hub/nodes/esp32s3-abc/node_id"] == "kitchen"
    assert published["mic_hub/nodes/esp32s3-abc/packets_missing"] == "0"


def test_discovery_payloads_include_control_topics() -> None:
    bridge, client, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=95.0)

    bridge._publish_initial_state()

    published = {topic: payload for topic, payload, _qos, _retain in client.published}
    streaming_on_payload = json.loads(
        published["homeassistant/button/pc-hub-test/esp32s3_abc_streaming_on/config"]
    )
    streaming_off_payload = json.loads(
        published["homeassistant/button/pc-hub-test/esp32s3_abc_streaming_off/config"]
    )
    button_payload = json.loads(
        published["homeassistant/button/pc-hub-test/esp32s3_abc_restart/config"]
    )

    assert streaming_on_payload["command_topic"] == "mic/esp32s3-abc/cmd/streaming/set"
    assert streaming_on_payload["payload_press"] == "ON"
    assert streaming_on_payload["availability_mode"] == "all"
    assert streaming_on_payload["availability"] == [
        {"topic": "mic_hub/status/availability", "payload_available": "online", "payload_not_available": "offline"},
        {"topic": "mic_hub/nodes/esp32s3-abc/online", "payload_available": "online", "payload_not_available": "offline"},
    ]
    assert streaming_off_payload["command_topic"] == "mic/esp32s3-abc/cmd/streaming/set"
    assert streaming_off_payload["payload_press"] == "OFF"
    assert streaming_off_payload["availability_mode"] == "all"
    assert streaming_off_payload["availability"] == [
        {"topic": "mic_hub/status/availability", "payload_available": "online", "payload_not_available": "offline"},
        {"topic": "mic_hub/nodes/esp32s3-abc/online", "payload_available": "online", "payload_not_available": "offline"},
    ]
    assert button_payload["command_topic"] == "mic/esp32s3-abc/cmd/restart"
    assert button_payload["payload_press"] == "restart"
    assert button_payload["availability_mode"] == "all"
    assert button_payload["availability"] == [
        {"topic": "mic_hub/status/availability", "payload_available": "online", "payload_not_available": "offline"},
        {"topic": "mic_hub/nodes/esp32s3-abc/online", "payload_available": "online", "payload_not_available": "offline"},
    ]


def test_new_nodes_get_discovery_without_restart() -> None:
    bridge, client, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=95.0, node_uuid="esp32s3-abc", node_id="kitchen")
    bridge._publish_initial_state()

    _register_node(registry, last_seen=99.0, node_uuid="esp32s3-def", node_id="office")
    bridge._publish_state()

    topics = [topic for topic, _payload, _qos, _retain in client.published]
    assert "homeassistant/binary_sensor/pc-hub-test/esp32s3_def_online/config" in topics
    assert "mic_hub/nodes/esp32s3-def/online" in topics


def test_node_is_marked_offline_after_threshold() -> None:
    bridge, client, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=60.0)

    bridge._publish_initial_state()

    published = {topic: payload for topic, payload, _qos, _retain in client.published}
    assert published["mic_hub/status/online_nodes"] == "0"
    assert published["mic_hub/nodes/esp32s3-abc/online"] == "offline"


def test_discovery_is_not_republished_on_periodic_state_publish() -> None:
    bridge, client, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=95.0)

    bridge._publish_initial_state()
    first_discovery_count = sum(1 for topic, _payload, _qos, _retain in client.published if topic.endswith("/config"))

    bridge._publish_state()
    second_discovery_count = sum(1 for topic, _payload, _qos, _retain in client.published if topic.endswith("/config"))

    assert first_discovery_count == second_discovery_count


def test_node_rename_republishes_discovery() -> None:
    bridge, client, registry = _bridge(now=100.0)
    _register_node(registry, last_seen=95.0, node_uuid="esp32s3-abc", node_id="kitchen")
    bridge._publish_initial_state()
    initial_discovery_count = sum(1 for topic, _payload, _qos, _retain in client.published if topic.endswith("/config"))

    _register_node(registry, last_seen=99.0, node_uuid="esp32s3-abc", node_id="office")
    bridge._publish_state()
    updated_discovery_count = sum(1 for topic, _payload, _qos, _retain in client.published if topic.endswith("/config"))

    assert updated_discovery_count > initial_discovery_count


def test_start_failure_cleans_up_client_state() -> None:
    registry = NodeRegistry()
    client = _FailingClient()
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
    )

    import pytest

    with pytest.raises(RuntimeError, match="connect failed"):
        bridge.start()

    assert client.loop_stopped is True
    assert client.disconnected is True


def test_missing_known_node_is_published_offline() -> None:
    node = NodeState(
        node_uuid="esp32s3-abc",
        node_id="kitchen",
        last_seen=95.0,
        last_seq=10,
        packets_received=1,
    )
    registry = _RegistryStub([node])
    client = _FakeClient()
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,  # type: ignore[arg-type]
        mqtt_client=client,
        now_fn=lambda: 100.0,
    )

    bridge._publish_initial_state()
    registry.nodes = []
    bridge._publish_state()

    online_payloads = [payload for topic, payload, _qos, _retain in client.published if topic == "mic_hub/nodes/esp32s3-abc/online"]
    assert online_payloads[-1] == "offline"


def test_thread_failure_leaves_bridge_not_running() -> None:
    registry = NodeRegistry()
    client = _FakeClient()
    bridge = _ThreadFailureBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
    )

    bridge.start()
    if bridge._thread is not None:
        bridge._thread.join(timeout=1)

    assert bridge.is_running is False


def test_start_reconciles_retained_online_topics_missing_from_registry(monkeypatch) -> None:
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_QUIET_PERIOD_SECONDS", 0.0)
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_TIMEOUT_SECONDS", 0.01)
    registry = _RegistryStub([])
    client = _RetainedClient(["mic_hub/nodes/esp32s3-stale/online"])
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,  # type: ignore[arg-type]
        mqtt_client=client,
        now_fn=time.monotonic,
    )

    bridge.start()
    bridge.stop()

    stale_payloads = [
        (payload, retain)
        for topic, payload, _qos, retain in client.published
        if topic == "mic_hub/nodes/esp32s3-stale/online"
    ]
    assert ("offline", True) in stale_payloads


def test_start_keeps_current_registry_node_online_when_broker_replays_same_topic(monkeypatch) -> None:
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_QUIET_PERIOD_SECONDS", 0.0)
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_TIMEOUT_SECONDS", 0.01)
    registry = NodeRegistry()
    _register_node(registry, last_seen=time.monotonic())
    client = _RetainedClient(["mic_hub/nodes/esp32s3-abc/online"])
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
        now_fn=time.monotonic,
    )

    bridge.start()
    bridge.stop()

    online_payloads = [
        payload
        for topic, payload, _qos, _retain in client.published
        if topic == "mic_hub/nodes/esp32s3-abc/online"
    ]
    assert online_payloads[0] == "online"
    assert "offline" not in online_payloads[:-1]


def test_subscribe_failure_aborts_bridge_start() -> None:
    registry = NodeRegistry()
    client = _SubscribeFailingClient()
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
    )

    import pytest

    with pytest.raises(RuntimeError, match="failed to subscribe"):
        bridge.start()

    assert bridge.is_running is False
    assert client.loop_stopped is True
    assert client.disconnected is True


def test_start_waits_for_delayed_retained_messages(monkeypatch) -> None:
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_QUIET_PERIOD_SECONDS", 0.02)
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_TIMEOUT_SECONDS", 0.2)
    registry = _RegistryStub([])
    client = _DelayedRetainedClient(["mic_hub/nodes/esp32s3-delayed/online"], delay_seconds=0.05)
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,  # type: ignore[arg-type]
        mqtt_client=client,
        now_fn=time.monotonic,
    )

    bridge.start()
    bridge.stop()

    delayed_payloads = [
        payload
        for topic, payload, _qos, _retain in client.published
        if topic == "mic_hub/nodes/esp32s3-delayed/online"
    ]
    assert delayed_payloads[-1] == "offline"


def test_start_succeeds_when_no_retained_messages_exist(monkeypatch) -> None:
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_QUIET_PERIOD_SECONDS", 0.02)
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_TIMEOUT_SECONDS", 0.05)
    registry = NodeRegistry()
    client = _FakeClient()
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
        now_fn=time.monotonic,
    )

    bridge.start()
    assert bridge.is_running is True
    bridge.stop()


def test_start_fails_when_retained_stream_never_quiets(monkeypatch) -> None:
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_QUIET_PERIOD_SECONDS", 0.05)
    monkeypatch.setattr(ha_mqtt_module, "RECONCILE_TIMEOUT_SECONDS", 0.06)
    registry = NodeRegistry()
    client = _NoisyRetainedClient()
    bridge = HaMqttBridge(
        config=HaMqttBridgeConfig(
            host="mqtt.local",
            port=1883,
            username="user",
            password="pass",
            client_id="pc-hub-test",
            discovery_prefix="homeassistant",
            topic_prefix="mic_hub",
            node_offline_seconds=30,
        ),
        registry=registry,
        mqtt_client=client,
        now_fn=time.monotonic,
    )

    import pytest

    with pytest.raises(RuntimeError, match="timed out while waiting for retained MQTT reconcile messages"):
        bridge.start()

    assert bridge.is_running is False
