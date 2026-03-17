#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "esp_err.h"

#define DEVICE_CONFIG_NAMESPACE "device_cfg"
#define DEVICE_CONFIG_NODE_UUID_MAX_LEN 32
#define DEVICE_CONFIG_NODE_ID_MAX_LEN 32
#define DEVICE_CONFIG_HOST_MAX_LEN 64

typedef uint32_t device_config_actions_t;

#define DEVICE_CONFIG_ACTION_NONE 0U
#define DEVICE_CONFIG_ACTION_APPLY_STREAMING (1U << 0)
#define DEVICE_CONFIG_ACTION_APPLY_UDP_TARGET (1U << 1)
#define DEVICE_CONFIG_ACTION_RESTART_REQUIRED (1U << 2)

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
    bool is_configured;
} device_config_t;

typedef struct {
    char wifi_ssid[33];
    char wifi_password[65];
    char mqtt_host[DEVICE_CONFIG_HOST_MAX_LEN];
    uint16_t mqtt_port;
    char mqtt_username[33];
    char mqtt_password[65];
    char udp_host[DEVICE_CONFIG_HOST_MAX_LEN];
    uint16_t udp_port;
    char node_id[DEVICE_CONFIG_NODE_ID_MAX_LEN];
} device_setup_config_t;

esp_err_t device_config_init(void);
const device_config_t *device_config_get(void);
bool device_config_is_configured(void);
esp_err_t device_config_commit_streaming_enabled(bool enabled, device_config_actions_t *actions);
esp_err_t device_config_commit_udp_target(const char *host, uint16_t port, device_config_actions_t *actions);
esp_err_t device_config_commit_setup(const device_setup_config_t *setup, device_config_actions_t *actions);
