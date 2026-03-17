#include "mqtt_control.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "audio_capture.h"
#include "device_config.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "health_monitor.h"
#include "mqtt_client.h"
#include "udp_streamer.h"

static const char *TAG = "mqtt_control";
static esp_mqtt_client_handle_t s_client;
static bool s_network_ready;
static bool s_mqtt_started;
static char s_broker_uri[128];
static char s_availability_topic[96];

static void make_topic(char *buffer, size_t buffer_len, const char *suffix) {
    snprintf(buffer, buffer_len, "mic/%s/%s", device_config_get()->node_uuid, suffix);
}

static void publish_text(const char *suffix, const char *payload, int qos, bool retain) {
    if (s_client == NULL) {
        return;
    }
    char topic[96];
    make_topic(topic, sizeof(topic), suffix);
    esp_mqtt_client_publish(s_client, topic, payload, 0, qos, retain ? 1 : 0);
}

static void publish_u32(const char *suffix, uint32_t value, int qos, bool retain) {
    char payload[16];
    snprintf(payload, sizeof(payload), "%" PRIu32, value);
    publish_text(suffix, payload, qos, retain);
}

static void publish_i32(const char *suffix, int32_t value, int qos, bool retain) {
    char payload[16];
    snprintf(payload, sizeof(payload), "%" PRId32, value);
    publish_text(suffix, payload, qos, retain);
}

static void publish_udp_target(void) {
    char payload[96];
    snprintf(payload, sizeof(payload), "%s:%u", device_config_get()->udp_host, device_config_get()->udp_port);
    publish_text("status/udp_target", payload, 1, true);
}

static void publish_snapshot(void) {
    health_snapshot_t snapshot = health_monitor_get_snapshot();
    publish_text("status/node_id", device_config_get()->node_id, 1, true);
    publish_text("status/node_uuid", device_config_get()->node_uuid, 1, true);
    publish_text("status/streaming", snapshot.streaming_enabled ? "ON" : "OFF", 1, true);
    publish_i32("status/rssi", snapshot.wifi_rssi, 0, false);
    publish_u32("status/packets_sent", snapshot.packets_sent, 0, false);
    publish_u32("status/packets_dropped", snapshot.packets_dropped, 0, false);
    publish_u32("status/uptime", (uint32_t)(snapshot.uptime_ms / 1000ULL), 0, false);
    publish_udp_target();
}

static void handle_streaming_command(const char *payload, size_t len) {
    if (len == 2 && strncasecmp(payload, "ON", 2) == 0) {
        device_config_set_streaming_enabled(true);
        audio_capture_set_streaming_enabled(true);
        health_monitor_set_streaming_enabled(true);
        publish_text("status/streaming", "ON", 1, true);
        return;
    }
    if (len == 3 && strncasecmp(payload, "OFF", 3) == 0) {
        device_config_set_streaming_enabled(false);
        audio_capture_set_streaming_enabled(false);
        health_monitor_set_streaming_enabled(false);
        publish_text("status/streaming", "OFF", 1, true);
    }
}

static void handle_restart_command(void) {
    publish_text("status/availability", "offline", 1, true);
    vTaskDelay(pdMS_TO_TICKS(200));
    esp_restart();
}

static void handle_udp_target_command(const char *payload, size_t len) {
    char buffer[96];
    if (len >= sizeof(buffer)) {
        return;
    }
    memcpy(buffer, payload, len);
    buffer[len] = '\0';

    char *colon = strrchr(buffer, ':');
    if (colon == NULL) {
        return;
    }
    *colon = '\0';
    long port = strtol(colon + 1, NULL, 10);
    if (port <= 0 || port > 65535) {
        return;
    }

    if (device_config_set_udp_target(buffer, (uint16_t)port) == ESP_OK &&
        udp_streamer_reconfigure_target() == ESP_OK) {
        publish_udp_target();
    }
}

static void subscribe_command_topics(void) {
    char topic[96];

    make_topic(topic, sizeof(topic), "cmd/streaming/set");
    esp_mqtt_client_subscribe(s_client, topic, 1);

    make_topic(topic, sizeof(topic), "cmd/restart");
    esp_mqtt_client_subscribe(s_client, topic, 1);

    make_topic(topic, sizeof(topic), "cmd/udp_target/set");
    esp_mqtt_client_subscribe(s_client, topic, 1);
}

static void mqtt_event_handler(void *handler_args,
                               esp_event_base_t base,
                               int32_t event_id,
                               void *event_data) {
    (void)handler_args;
    (void)base;

    esp_mqtt_event_handle_t event = event_data;
    char topic[96];

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected");
        health_monitor_set_mqtt_connected(true);
        publish_text("status/availability", "online", 1, true);
        subscribe_command_topics();
        publish_snapshot();
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT disconnected");
        health_monitor_set_mqtt_connected(false);
        break;
    case MQTT_EVENT_DATA:
        make_topic(topic, sizeof(topic), "cmd/streaming/set");
        if ((int)strlen(topic) == event->topic_len && strncmp(topic, event->topic, event->topic_len) == 0) {
            handle_streaming_command(event->data, (size_t)event->data_len);
            return;
        }
        make_topic(topic, sizeof(topic), "cmd/restart");
        if ((int)strlen(topic) == event->topic_len && strncmp(topic, event->topic, event->topic_len) == 0) {
            handle_restart_command();
            return;
        }
        make_topic(topic, sizeof(topic), "cmd/udp_target/set");
        if ((int)strlen(topic) == event->topic_len && strncmp(topic, event->topic, event->topic_len) == 0) {
            handle_udp_target_command(event->data, (size_t)event->data_len);
        }
        break;
    default:
        break;
    }
}

esp_err_t mqtt_control_init(void) {
    const device_config_t *config = device_config_get();

    snprintf(s_broker_uri, sizeof(s_broker_uri), "mqtt://%s:%u", config->mqtt_host, config->mqtt_port);
    make_topic(s_availability_topic, sizeof(s_availability_topic), "status/availability");

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = s_broker_uri,
        .credentials.username = config->mqtt_username,
        .credentials.authentication.password = config->mqtt_password,
        .session.keepalive = 30,
        .session.last_will.topic = s_availability_topic,
        .session.last_will.msg = "offline",
        .session.last_will.msg_len = 7,
        .session.last_will.retain = 1,
        .session.last_will.qos = 1,
    };

    s_client = esp_mqtt_client_init(&mqtt_cfg);
    if (s_client == NULL) {
        return ESP_FAIL;
    }

    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    if (s_network_ready) {
        esp_mqtt_client_start(s_client);
        s_mqtt_started = true;
    }
    return ESP_OK;
}

void mqtt_control_set_network_ready(bool ready) {
    s_network_ready = ready;
    if (s_client == NULL) {
        return;
    }
    if (ready) {
        if (!s_mqtt_started) {
            esp_mqtt_client_start(s_client);
            s_mqtt_started = true;
        } else {
            esp_mqtt_client_reconnect(s_client);
        }
    } else {
        if (s_mqtt_started) {
            esp_mqtt_client_stop(s_client);
            s_mqtt_started = false;
        }
        health_monitor_set_mqtt_connected(false);
    }
}

void mqtt_control_publish_boot_state(void) {
    health_monitor_set_streaming_enabled(device_config_get()->streaming_enabled);
    if (s_client != NULL) {
        publish_snapshot();
    }
}
