#include "device_config.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_mac.h"
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "device_secrets_defaults.h"

static const char *TAG = "device_config";

static device_config_t s_config = {
    .wifi_ssid = DEVICE_SECRET_WIFI_SSID,
    .wifi_password = DEVICE_SECRET_WIFI_PASS,
    .mqtt_host = DEVICE_SECRET_MQTT_HOST,
    .mqtt_port = DEVICE_SECRET_MQTT_PORT,
    .mqtt_username = DEVICE_SECRET_MQTT_USER,
    .mqtt_password = DEVICE_SECRET_MQTT_PASS,
    .udp_host = DEVICE_SECRET_UDP_HOST,
    .udp_port = DEVICE_SECRET_UDP_PORT,
    .node_uuid = "",
    .node_id = DEVICE_SECRET_NODE_ID,
    .i2s_bclk_pin = GPIO_NUM_4,
    .i2s_ws_pin = GPIO_NUM_5,
    .i2s_din_pin = GPIO_NUM_6,
    .streaming_enabled = true,
    .telemetry_interval_ms = 10000,
    .is_configured = false,
};

static void load_string(nvs_handle_t handle, const char *key, char *buffer, size_t buffer_len) {
    size_t required = buffer_len;
    esp_err_t err = nvs_get_str(handle, key, buffer, &required);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to load %s: %s", key, esp_err_to_name(err));
    }
}

static esp_err_t derive_node_uuid(char *buffer, size_t buffer_len) {
    uint8_t mac[6] = {0};
    esp_err_t err = esp_read_mac(mac, ESP_MAC_WIFI_STA);
    if (err != ESP_OK) {
        return err;
    }

    int written = snprintf(buffer,
                           buffer_len,
                           "esp32s3-%02x%02x%02x%02x%02x%02x",
                           mac[0],
                           mac[1],
                           mac[2],
                           mac[3],
                           mac[4],
                           mac[5]);
    return (written > 0 && (size_t)written < buffer_len) ? ESP_OK : ESP_ERR_INVALID_SIZE;
}

static bool has_required_setup_fields(const device_config_t *config) {
    return config->wifi_ssid[0] != '\0' &&
           config->mqtt_host[0] != '\0' &&
           config->udp_host[0] != '\0' &&
           config->node_id[0] != '\0' &&
           config->mqtt_port != 0 &&
           config->udp_port != 0;
}

static esp_err_t save_string(nvs_handle_t handle, const char *key, const char *value) {
    if (value == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    return nvs_set_str(handle, key, value);
}

static void assign_actions(device_config_actions_t *actions, device_config_actions_t value) {
    if (actions != NULL) {
        *actions = value;
    }
}

esp_err_t device_config_init(void) {
    esp_err_t err = derive_node_uuid(s_config.node_uuid, sizeof(s_config.node_uuid));
    if (err != ESP_OK) {
        return err;
    }

    nvs_handle_t handle;
    err = nvs_open(DEVICE_CONFIG_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }

    load_string(handle, "wifi_ssid", s_config.wifi_ssid, sizeof(s_config.wifi_ssid));
    load_string(handle, "wifi_pass", s_config.wifi_password, sizeof(s_config.wifi_password));
    load_string(handle, "mqtt_host", s_config.mqtt_host, sizeof(s_config.mqtt_host));
    load_string(handle, "mqtt_user", s_config.mqtt_username, sizeof(s_config.mqtt_username));
    load_string(handle, "mqtt_pass", s_config.mqtt_password, sizeof(s_config.mqtt_password));
    load_string(handle, "udp_host", s_config.udp_host, sizeof(s_config.udp_host));
    load_string(handle, "node_id", s_config.node_id, sizeof(s_config.node_id));

    uint16_t port16 = 0;
    err = nvs_get_u16(handle, "mqtt_port", &port16);
    if (err == ESP_OK) {
        s_config.mqtt_port = port16;
    }
    err = nvs_get_u16(handle, "udp_port", &port16);
    if (err == ESP_OK) {
        s_config.udp_port = port16;
    }

    uint8_t enabled = s_config.streaming_enabled ? 1U : 0U;
    err = nvs_get_u8(handle, "streaming", &enabled);
    if (err == ESP_OK) {
        s_config.streaming_enabled = enabled != 0U;
    }

    uint32_t interval = 0;
    err = nvs_get_u32(handle, "telemetry_ms", &interval);
    if (err == ESP_OK && interval >= 1000U) {
        s_config.telemetry_interval_ms = interval;
    }

    nvs_close(handle);
    s_config.is_configured = has_required_setup_fields(&s_config);
    return ESP_OK;
}

const device_config_t *device_config_get(void) {
    return &s_config;
}

bool device_config_is_configured(void) {
    return s_config.is_configured;
}

esp_err_t device_config_commit_streaming_enabled(bool enabled, device_config_actions_t *actions) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(DEVICE_CONFIG_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }

    err = nvs_set_u8(handle, "streaming", enabled ? 1U : 0U);
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    if (err != ESP_OK) {
        return err;
    }

    s_config.streaming_enabled = enabled;
    assign_actions(actions, DEVICE_CONFIG_ACTION_APPLY_STREAMING);
    return err;
}

esp_err_t device_config_commit_udp_target(const char *host, uint16_t port, device_config_actions_t *actions) {
    if (host == NULL || host[0] == '\0' || port == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open(DEVICE_CONFIG_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }

    err = nvs_set_str(handle, "udp_host", host);
    if (err == ESP_OK) {
        err = nvs_set_u16(handle, "udp_port", port);
    }
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    if (err != ESP_OK) {
        return err;
    }

    snprintf(s_config.udp_host, sizeof(s_config.udp_host), "%s", host);
    s_config.udp_port = port;
    assign_actions(actions, DEVICE_CONFIG_ACTION_APPLY_UDP_TARGET);
    return ESP_OK;
}

esp_err_t device_config_commit_setup(const device_setup_config_t *setup, device_config_actions_t *actions) {
    if (setup == NULL ||
        setup->wifi_ssid[0] == '\0' ||
        setup->mqtt_host[0] == '\0' ||
        setup->udp_host[0] == '\0' ||
        setup->node_id[0] == '\0' ||
        setup->mqtt_port == 0 ||
        setup->udp_port == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open(DEVICE_CONFIG_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }

    err = save_string(handle, "wifi_ssid", setup->wifi_ssid);
    if (err == ESP_OK) {
        err = save_string(handle, "wifi_pass", setup->wifi_password);
    }
    if (err == ESP_OK) {
        err = save_string(handle, "mqtt_host", setup->mqtt_host);
    }
    if (err == ESP_OK) {
        err = nvs_set_u16(handle, "mqtt_port", setup->mqtt_port);
    }
    if (err == ESP_OK) {
        err = save_string(handle, "mqtt_user", setup->mqtt_username);
    }
    if (err == ESP_OK) {
        err = save_string(handle, "mqtt_pass", setup->mqtt_password);
    }
    if (err == ESP_OK) {
        err = save_string(handle, "udp_host", setup->udp_host);
    }
    if (err == ESP_OK) {
        err = nvs_set_u16(handle, "udp_port", setup->udp_port);
    }
    if (err == ESP_OK) {
        err = save_string(handle, "node_id", setup->node_id);
    }
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    if (err != ESP_OK) {
        return err;
    }

    strlcpy(s_config.wifi_ssid, setup->wifi_ssid, sizeof(s_config.wifi_ssid));
    strlcpy(s_config.wifi_password, setup->wifi_password, sizeof(s_config.wifi_password));
    strlcpy(s_config.mqtt_host, setup->mqtt_host, sizeof(s_config.mqtt_host));
    s_config.mqtt_port = setup->mqtt_port;
    strlcpy(s_config.mqtt_username, setup->mqtt_username, sizeof(s_config.mqtt_username));
    strlcpy(s_config.mqtt_password, setup->mqtt_password, sizeof(s_config.mqtt_password));
    strlcpy(s_config.udp_host, setup->udp_host, sizeof(s_config.udp_host));
    s_config.udp_port = setup->udp_port;
    strlcpy(s_config.node_id, setup->node_id, sizeof(s_config.node_id));
    s_config.is_configured = true;

    ESP_LOGI(TAG, "Saved provisioning for node_id=%s udp=%s:%u mqtt=%s:%u",
             s_config.node_id,
             s_config.udp_host,
             s_config.udp_port,
             s_config.mqtt_host,
             s_config.mqtt_port);
    assign_actions(actions, DEVICE_CONFIG_ACTION_RESTART_REQUIRED);
    return ESP_OK;
}
