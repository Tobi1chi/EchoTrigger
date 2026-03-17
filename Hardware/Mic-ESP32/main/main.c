#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "audio_capture.h"
#include "audio_protocol.h"
#include "device_config.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "health_monitor.h"
#include "mqtt_control.h"
#include "nvs_flash.h"
#include "udp_streamer.h"

static const char *TAG = "main";
static EventGroupHandle_t s_network_events;
static StaticTask_t s_telemetry_task_buffer;
static StackType_t s_telemetry_task_stack[4096];
static esp_event_handler_instance_t s_wifi_handler_instance;
static esp_event_handler_instance_t s_ip_handler_instance;

#define WIFI_CONNECTED_BIT BIT0

static QueueHandle_t s_packet_queue;

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

static esp_err_t wifi_init_sta(void) {
    const device_config_t *config = device_config_get();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

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
    return ESP_OK;
}

static void telemetry_task(void *arg) {
    (void)arg;

    while (true) {
        EventBits_t bits = xEventGroupGetBits(s_network_events);
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

    s_network_events = xEventGroupCreate();
    s_packet_queue = xQueueCreate(8, sizeof(audio_packet_t));
    if (s_packet_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create packet queue");
        abort();
    }

    ESP_LOGI(TAG, "Booting node_id=%s node_uuid=%s udp=%s:%u mqtt=%s:%u",
             device_config_get()->node_id,
             device_config_get()->node_uuid,
             device_config_get()->udp_host,
             device_config_get()->udp_port,
             device_config_get()->mqtt_host,
             device_config_get()->mqtt_port);

    ESP_ERROR_CHECK(wifi_init_sta());
    ESP_ERROR_CHECK(udp_streamer_init(s_packet_queue));
    ESP_ERROR_CHECK(mqtt_control_init());
    ESP_ERROR_CHECK(audio_capture_init(s_packet_queue));

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
}
