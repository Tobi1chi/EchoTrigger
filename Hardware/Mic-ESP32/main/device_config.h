#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "esp_err.h"

#define DEVICE_CONFIG_NAMESPACE "device_cfg"
#define DEVICE_CONFIG_NODE_UUID_MAX_LEN 32
#define DEVICE_CONFIG_NODE_ID_MAX_LEN 32
#define DEVICE_CONFIG_HOST_MAX_LEN 64

typedef struct {
    char wifi_ssid[33];
    char wifi_password[65];
    char mqtt_host[DEVICE_CONFIG_HOST_MAX_LEN];
    uint16_t mqtt_port;
    char mqtt_username[33];
    char mqtt_password[65];
    char udp_host[DEVICE_CONFIG_HOST_MAX_LEN];
    uint16_t udp_port;
    char node_uuid[DEVICE_CONFIG_NODE_UUID_MAX_LEN];
    char node_id[DEVICE_CONFIG_NODE_ID_MAX_LEN];
    gpio_num_t i2s_bclk_pin;
    gpio_num_t i2s_ws_pin;
    gpio_num_t i2s_din_pin;
    bool streaming_enabled;
    uint32_t telemetry_interval_ms;
} device_config_t;

esp_err_t device_config_init(void);
const device_config_t *device_config_get(void);
esp_err_t device_config_set_streaming_enabled(bool enabled);
esp_err_t device_config_set_udp_target(const char *host, uint16_t port);
