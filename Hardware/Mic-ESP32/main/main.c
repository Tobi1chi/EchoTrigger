#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "audio_capture.h"
#include "audio_protocol.h"
#include "device_config.h"
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "health_monitor.h"
#include "mqtt_control.h"
#include "nvs_flash.h"
#include "setup_portal.h"
#include "udp_streamer.h"

static const char *TAG = "main";
static const TickType_t SETUP_PORTAL_RETRY_DELAY_TICKS = pdMS_TO_TICKS(2000);
static const TickType_t SETUP_BUTTON_POLL_TICKS = pdMS_TO_TICKS(100);
static const TickType_t SETUP_BUTTON_HOLD_TICKS = pdMS_TO_TICKS(5000);
static const UBaseType_t AUDIO_PACKET_QUEUE_DEPTH = 16;
static EventGroupHandle_t s_network_events;
static StaticTask_t s_telemetry_task_buffer;
static StackType_t s_telemetry_task_stack[4096];
static esp_event_handler_instance_t s_wifi_handler_instance;
static esp_event_handler_instance_t s_ip_handler_instance;

#define WIFI_CONNECTED_BIT BIT0

static QueueHandle_t s_packet_queue;
static bool s_network_stack_initialized;

static void log_setup_portal_error(const char *context, esp_err_t err) {
    ESP_LOGE(TAG, "%s setup portal failed: %s", context, esp_err_to_name(err));
}

static void restart_after_setup_portal_failure(void) {
    ESP_LOGW(TAG, "Retrying setup mode after %" PRIu32 " ms", (uint32_t)pdTICKS_TO_MS(SETUP_PORTAL_RETRY_DELAY_TICKS));
    vTaskDelay(SETUP_PORTAL_RETRY_DELAY_TICKS);
    esp_restart();
}

static bool should_force_setup_portal(void) {
    const gpio_num_t setup_button_gpio = device_config_get()->setup_button_pin;
    const gpio_config_t config = {
        .pin_bit_mask = 1ULL << setup_button_gpio,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&config));

    ESP_LOGI(TAG, "Checking setup button on GPIO %d for forced setup mode", (int)setup_button_gpio);
    if (gpio_get_level(setup_button_gpio) != 0) {
        return false;
    }

    ESP_LOGI(TAG, "Setup button held, waiting for long-press threshold");
    TickType_t elapsed = 0;
    while (elapsed < SETUP_BUTTON_HOLD_TICKS) {
        if (gpio_get_level(setup_button_gpio) != 0) {
            ESP_LOGI(TAG, "Setup button released before threshold, continuing normal startup");
            return false;
        }
        vTaskDelay(SETUP_BUTTON_POLL_TICKS);
        elapsed += SETUP_BUTTON_POLL_TICKS;
    }

    ESP_LOGW(TAG, "Setup button held for 5s, forcing AP setup portal");
    return true;
}

static void wifi_event_handler(void *arg,
                               esp_event_base_t event_base,
                               int32_t event_id,
                               void *event_data) {
    (void)arg;
    (void)event_data;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
        return;
    }

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_network_events, WIFI_CONNECTED_BIT);
        health_monitor_set_wifi_connected(false);
        udp_streamer_set_network_ready(false);
        mqtt_control_set_network_ready(false);
        esp_wifi_connect();
        return;
    }

    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_network_events, WIFI_CONNECTED_BIT);
        health_monitor_set_wifi_connected(true);
        udp_streamer_set_network_ready(true);
        mqtt_control_set_network_ready(true);

        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            health_monitor_set_wifi_rssi(ap_info.rssi);
        }
    }
}

static esp_err_t network_stack_init(void) {
    if (s_network_stack_initialized) {
        return ESP_OK;
    }
    ESP_LOGI(TAG, "Initializing network stack");
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    s_network_stack_initialized = true;
    ESP_LOGI(TAG, "Network stack initialized");
    return ESP_OK;
}

static esp_err_t wifi_init_sta(void) {
    const device_config_t *config = device_config_get();

    ESP_LOGI(TAG, "Initializing Wi-Fi station mode");
    ESP_ERROR_CHECK(network_stack_init());
    esp_netif_create_default_wifi_sta();

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        &s_wifi_handler_instance));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        &s_ip_handler_instance));

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.sta.ssid, config->wifi_ssid, sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, config->wifi_password, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    wifi_config.sta.pmf_cfg.capable = true;
    wifi_config.sta.pmf_cfg.required = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "Wi-Fi station mode started");
    return ESP_OK;
}

static void telemetry_task(void *arg) {
    (void)arg;

    while (true) {
        EventBits_t bits = xEventGroupGetBits(s_network_events);
        health_snapshot_t snapshot = health_monitor_get_snapshot();
        UBaseType_t queue_fill = s_packet_queue != NULL ? uxQueueMessagesWaiting(s_packet_queue) : 0;
        UBaseType_t audio_hwm = 0;
        UBaseType_t udp_hwm = 0;
        UBaseType_t mqtt_hwm = 0;

        TaskHandle_t audio_task = audio_capture_get_task_handle();
        if (audio_task != NULL) {
            audio_hwm = uxTaskGetStackHighWaterMark(audio_task);
        }

        TaskHandle_t udp_task = udp_streamer_get_task_handle();
        if (udp_task != NULL) {
            udp_hwm = uxTaskGetStackHighWaterMark(udp_task);
        }

        TaskHandle_t mqtt_task = mqtt_control_get_task_handle();
        if (mqtt_task != NULL) {
            mqtt_hwm = uxTaskGetStackHighWaterMark(mqtt_task);
        }

        ESP_LOGI(TAG,
                 "Runtime stats: heap=%" PRIu32 "B queue=%u/%u peak=%" PRIu32 " dropped=%" PRIu32 " udp_errors=%" PRIu32
                 " stack_hwm(words): audio=%u udp=%u mqtt=%u telemetry=%u",
                 (uint32_t)esp_get_free_heap_size(),
                 (unsigned)queue_fill,
                 (unsigned)AUDIO_PACKET_QUEUE_DEPTH,
                 snapshot.max_queue_fill_seen,
                 snapshot.packets_dropped,
                 snapshot.udp_errors,
                 (unsigned)audio_hwm,
                 (unsigned)udp_hwm,
                 (unsigned)mqtt_hwm,
                 (unsigned)uxTaskGetStackHighWaterMark(NULL));
        if ((bits & WIFI_CONNECTED_BIT) != 0) {
            wifi_ap_record_t ap_info;
            if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
                health_monitor_set_wifi_rssi(ap_info.rssi);
            }
            mqtt_control_publish_boot_state();
        }
        vTaskDelay(pdMS_TO_TICKS(device_config_get()->telemetry_interval_ms));
    }
}

void app_main(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(device_config_init());
    health_monitor_init();
    health_monitor_set_streaming_enabled(device_config_get()->streaming_enabled);

    ESP_LOGI(TAG, "Booting node_id=%s node_uuid=%s udp=%s:%u mqtt=%s:%u",
             device_config_get()->node_id,
             device_config_get()->node_uuid,
             device_config_get()->udp_host,
             device_config_get()->udp_port,
             device_config_get()->mqtt_host,
             device_config_get()->mqtt_port);

    const bool force_setup_portal = should_force_setup_portal();
    if (force_setup_portal || !device_config_is_configured()) {
        if (force_setup_portal) {
            ESP_LOGW(TAG, "Forcing AP setup portal for this boot");
        } else {
            ESP_LOGW(TAG, "Device is not provisioned; starting setup portal");
        }
        ESP_ERROR_CHECK(network_stack_init());
        err = setup_portal_start(SETUP_PORTAL_MODE_AP);
        if (err != ESP_OK) {
            log_setup_portal_error("AP-mode", err);
            ESP_LOGW(TAG, "AP-mode setup portal is required for provisioning; restarting to retry");
            restart_after_setup_portal_failure();
        }
        return;
    }

    s_network_events = xEventGroupCreate();
    s_packet_queue = xQueueCreate(AUDIO_PACKET_QUEUE_DEPTH, sizeof(audio_packet_t));
    if (s_packet_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create packet queue");
        abort();
    }
    ESP_LOGI(TAG, "Packet queue created with depth=%u", (unsigned)AUDIO_PACKET_QUEUE_DEPTH);

    ESP_ERROR_CHECK(wifi_init_sta());
    ESP_LOGI(TAG, "Starting STA setup portal");
    err = setup_portal_start(SETUP_PORTAL_MODE_STA);
    if (err != ESP_OK) {
        log_setup_portal_error("STA-mode", err);
        ESP_LOGW(TAG, "STA setup portal disabled due to startup error; continuing without local reconfiguration portal");
    } else {
        ESP_LOGI(TAG, "STA setup portal started");
    }
    ESP_ERROR_CHECK(udp_streamer_init(s_packet_queue));
    ESP_LOGI(TAG, "UDP streamer initialized");
    ESP_ERROR_CHECK(mqtt_control_init());
    ESP_LOGI(TAG, "MQTT control initialized");
    ESP_ERROR_CHECK(audio_capture_init(s_packet_queue));
    ESP_LOGI(TAG, "Audio capture initialized");

    TaskHandle_t telemetry_handle = xTaskCreateStaticPinnedToCore(telemetry_task,
                                                                  "telemetry_task",
                                                                  sizeof(s_telemetry_task_stack) / sizeof(StackType_t),
                                                                  NULL,
                                                                  4,
                                                                  s_telemetry_task_stack,
                                                                  &s_telemetry_task_buffer,
                                                                  tskNO_AFFINITY);
    if (telemetry_handle == NULL) {
        ESP_LOGE(TAG, "Failed to create telemetry task");
        abort();
    }
    ESP_LOGI(TAG, "Telemetry task created");
    ESP_LOGI(TAG, "System startup complete");
}
