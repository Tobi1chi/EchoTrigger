#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool wifi_connected;
    bool mqtt_connected;
    bool udp_ready;
    bool streaming_enabled;
    int8_t wifi_rssi;
    uint32_t packets_sent;
    uint32_t packets_dropped;
    uint32_t udp_errors;
    uint64_t uptime_ms;
} health_snapshot_t;

void health_monitor_init(void);
void health_monitor_set_wifi_connected(bool connected);
void health_monitor_set_mqtt_connected(bool connected);
void health_monitor_set_udp_ready(bool ready);
void health_monitor_set_streaming_enabled(bool enabled);
void health_monitor_set_wifi_rssi(int8_t rssi);
void health_monitor_increment_packets_sent(void);
void health_monitor_increment_packets_dropped(void);
void health_monitor_increment_udp_errors(void);
health_snapshot_t health_monitor_get_snapshot(void);
