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
#include "freertos/queue.h"
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
static QueueHandle_t s_command_queue;
static StaticTask_t s_control_task_buffer;
static StackType_t s_control_task_stack[4096];
static TaskHandle_t s_control_task_handle;

typedef enum {
    CONTROL_COMMAND_STREAMING = 0,
    CONTROL_COMMAND_RESTART = 1,
    CONTROL_COMMAND_UDP_TARGET = 2,
} control_command_type_t;

typedef struct {
    control_command_type_t type;
    bool streaming_enabled;
    char udp_host[DEVICE_CONFIG_HOST_MAX_LEN];
    uint16_t udp_port;
} control_command_t;

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
    publish_u32("status/udp_errors", snapshot.udp_errors, 0, false);
    publish_u32("status/queue_peak", snapshot.max_queue_fill_seen, 0, false);
    publish_u32("status/uptime", (uint32_t)(snapshot.uptime_ms / 1000ULL), 0, false);
    publish_udp_target();
}

static esp_err_t enqueue_command(const control_command_t *command) {
    if (s_command_queue == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    return xQueueSendToBack(s_command_queue, command, 0) == pdTRUE ? ESP_OK : ESP_ERR_NO_MEM;
}

static bool enqueue_command_or_log(const control_command_t *command, const char *source) {
    esp_err_t err = enqueue_command(command);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to queue %s command: %s", source, esp_err_to_name(err));
        return false;
    }
    return true;
}

static void apply_actions(device_config_actions_t actions) {
    if ((actions & DEVICE_CONFIG_ACTION_APPLY_STREAMING) != 0U) {
        bool enabled = device_config_get()->streaming_enabled;
        audio_capture_set_streaming_enabled(enabled);
        health_monitor_set_streaming_enabled(enabled);
        publish_text("status/streaming", enabled ? "ON" : "OFF", 1, true);
    }

    if ((actions & DEVICE_CONFIG_ACTION_APPLY_UDP_TARGET) != 0U) {
        if (udp_streamer_reconfigure_target() == ESP_OK) {
            publish_udp_target();
        } else {
            ESP_LOGE(TAG, "Failed to apply UDP target reconfiguration");
        }
    }

    if ((actions & DEVICE_CONFIG_ACTION_RESTART_REQUIRED) != 0U) {
        publish_text("status/availability", "offline", 1, true);
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
    }
}

static void control_task(void *arg) {
    (void)arg;

    control_command_t command;
    while (true) {
        if (xQueueReceive(s_command_queue, &command, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        device_config_actions_t actions = DEVICE_CONFIG_ACTION_NONE;
        esp_err_t err = ESP_OK;
        switch (command.type) {
        case CONTROL_COMMAND_STREAMING:
            err = device_config_commit_streaming_enabled(command.streaming_enabled, &actions);
            break;
        case CONTROL_COMMAND_UDP_TARGET:
            err = device_config_commit_udp_target(command.udp_host, command.udp_port, &actions);
            break;
        case CONTROL_COMMAND_RESTART:
            actions = DEVICE_CONFIG_ACTION_RESTART_REQUIRED;
            break;
        default:
            err = ESP_ERR_INVALID_ARG;
            break;
        }

        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Control command %d failed: %s", (int)command.type, esp_err_to_name(err));
            continue;
        }

        apply_actions(actions);
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
            control_command_t command = {0};
            command.type = CONTROL_COMMAND_STREAMING;
            if (event->data_len == 2 && strncasecmp(event->data, "ON", 2) == 0) {
                command.streaming_enabled = true;
                enqueue_command_or_log(&command, "streaming");
            } else if (event->data_len == 3 && strncasecmp(event->data, "OFF", 3) == 0) {
                command.streaming_enabled = false;
                enqueue_command_or_log(&command, "streaming");
            }
            return;
        }
        make_topic(topic, sizeof(topic), "cmd/restart");
        if ((int)strlen(topic) == event->topic_len && strncmp(topic, event->topic, event->topic_len) == 0) {
            control_command_t command = {.type = CONTROL_COMMAND_RESTART};
            enqueue_command_or_log(&command, "restart");
            return;
        }
        make_topic(topic, sizeof(topic), "cmd/udp_target/set");
        if ((int)strlen(topic) == event->topic_len && strncmp(topic, event->topic, event->topic_len) == 0) {
            char buffer[96];
            if (event->data_len > 0 && event->data_len < (int)sizeof(buffer)) {
                memcpy(buffer, event->data, (size_t)event->data_len);
                buffer[event->data_len] = '\0';

                char *colon = strrchr(buffer, ':');
                if (colon != NULL) {
                    *colon = '\0';
                    long port = strtol(colon + 1, NULL, 10);
                    if (port > 0 && port <= 65535) {
                        control_command_t command = {.type = CONTROL_COMMAND_UDP_TARGET, .udp_port = (uint16_t)port};
                        strlcpy(command.udp_host, buffer, sizeof(command.udp_host));
                        enqueue_command_or_log(&command, "udp_target");
                    }
                }
            }
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
    s_command_queue = xQueueCreate(8, sizeof(control_command_t));
    if (s_command_queue == NULL) {
        return ESP_ERR_NO_MEM;
    }
    s_control_task_handle = xTaskCreateStaticPinnedToCore(control_task,
                                                          "mqtt_control_task",
                                                          sizeof(s_control_task_stack) / sizeof(StackType_t),
                                                          NULL,
                                                          5,
                                                          s_control_task_stack,
                                                          &s_control_task_buffer,
                                                          tskNO_AFFINITY);
    if (s_control_task_handle == NULL) {
        return ESP_ERR_NO_MEM;
    }

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

TaskHandle_t mqtt_control_get_task_handle(void) {
    return s_control_task_handle;
}
