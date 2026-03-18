#include "health_monitor.h"

#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static SemaphoreHandle_t s_lock;
static health_snapshot_t s_state;

void health_monitor_init(void) {
    s_lock = xSemaphoreCreateMutex();
    memset(&s_state, 0, sizeof(s_state));
}

void health_monitor_set_wifi_connected(bool connected) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.wifi_connected = connected;
    xSemaphoreGive(s_lock);
}

void health_monitor_set_mqtt_connected(bool connected) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.mqtt_connected = connected;
    xSemaphoreGive(s_lock);
}

void health_monitor_set_udp_ready(bool ready) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.udp_ready = ready;
    xSemaphoreGive(s_lock);
}

void health_monitor_set_streaming_enabled(bool enabled) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.streaming_enabled = enabled;
    xSemaphoreGive(s_lock);
}

void health_monitor_set_wifi_rssi(int8_t rssi) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.wifi_rssi = rssi;
    xSemaphoreGive(s_lock);
}

void health_monitor_record_queue_fill(uint32_t fill) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (fill > s_state.max_queue_fill_seen) {
        s_state.max_queue_fill_seen = fill;
    }
    xSemaphoreGive(s_lock);
}

void health_monitor_increment_packets_sent(void) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.packets_sent++;
    xSemaphoreGive(s_lock);
}

void health_monitor_increment_packets_dropped(void) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.packets_dropped++;
    xSemaphoreGive(s_lock);
}

void health_monitor_increment_udp_errors(void) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.udp_errors++;
    xSemaphoreGive(s_lock);
}

health_snapshot_t health_monitor_get_snapshot(void) {
    xSemaphoreTake(s_lock, portMAX_DELAY);
    health_snapshot_t snapshot = s_state;
    snapshot.uptime_ms = (uint64_t)(esp_timer_get_time() / 1000);
    xSemaphoreGive(s_lock);
    return snapshot;
}
