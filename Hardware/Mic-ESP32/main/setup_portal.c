#include "setup_portal.h"

#include <ctype.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "device_config.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "health_monitor.h"

static const char *TAG = "setup_portal";
static const size_t SETUP_PORTAL_HTML_BUFFER_SIZE = 12288;
static httpd_handle_t s_http_server;
static setup_portal_mode_t s_mode = SETUP_PORTAL_MODE_AP;

static const char *portal_mode_name(setup_portal_mode_t mode) {
    return mode == SETUP_PORTAL_MODE_AP ? "AP" : "STA";
}

static void build_ap_identity(char *ssid, size_t ssid_len, char *password, size_t password_len) {
    const char *node_uuid = device_config_get()->node_uuid;
    size_t uuid_len = strlen(node_uuid);
    const char *suffix = uuid_len >= 6 ? node_uuid + uuid_len - 6 : node_uuid;

    snprintf(ssid, ssid_len, "MicSetup-%s", suffix);
    snprintf(password, password_len, "mic-setup");
}

static void get_sta_ip_string(char *buffer, size_t buffer_len) {
    strlcpy(buffer, "not connected", buffer_len);

    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (netif == NULL) {
        return;
    }

    esp_netif_ip_info_t ip_info;
    if (esp_netif_get_ip_info(netif, &ip_info) != ESP_OK || ip_info.ip.addr == 0) {
        return;
    }

    snprintf(buffer,
             buffer_len,
             IPSTR,
             IP2STR(&ip_info.ip));
}

static void html_escape(char *dest, size_t dest_len, const char *src) {
    size_t out = 0;
    if (dest_len == 0) {
        return;
    }

    while (*src != '\0' && out + 1 < dest_len) {
        const char *replacement = NULL;
        switch (*src) {
        case '&':
            replacement = "&amp;";
            break;
        case '<':
            replacement = "&lt;";
            break;
        case '>':
            replacement = "&gt;";
            break;
        case '"':
            replacement = "&quot;";
            break;
        case '\'':
            replacement = "&#39;";
            break;
        default:
            break;
        }

        if (replacement != NULL) {
            size_t len = strlen(replacement);
            if (out + len >= dest_len) {
                break;
            }
            memcpy(dest + out, replacement, len);
            out += len;
        } else {
            dest[out++] = *src;
        }
        src++;
    }

    dest[out] = '\0';
}

static void url_decode(char *dest, size_t dest_len, const char *src) {
    size_t out = 0;
    if (dest_len == 0) {
        return;
    }

    while (*src != '\0' && out + 1 < dest_len) {
        if (*src == '+') {
            dest[out++] = ' ';
            src++;
            continue;
        }

        if (*src == '%' && isxdigit((unsigned char)src[1]) && isxdigit((unsigned char)src[2])) {
            char hex[3] = {src[1], src[2], '\0'};
            dest[out++] = (char)strtol(hex, NULL, 16);
            src += 3;
            continue;
        }

        dest[out++] = *src++;
    }

    dest[out] = '\0';
}

static void apply_form_value(device_setup_config_t *setup, const char *key, const char *value) {
    if (strcmp(key, "wifi_ssid") == 0) {
        strlcpy(setup->wifi_ssid, value, sizeof(setup->wifi_ssid));
        return;
    }
    if (strcmp(key, "wifi_password") == 0) {
        if (value[0] != '\0') {
            strlcpy(setup->wifi_password, value, sizeof(setup->wifi_password));
        }
        return;
    }
    if (strcmp(key, "mqtt_host") == 0) {
        strlcpy(setup->mqtt_host, value, sizeof(setup->mqtt_host));
        return;
    }
    if (strcmp(key, "mqtt_port") == 0) {
        long port = strtol(value, NULL, 10);
        if (port > 0 && port <= 65535) {
            setup->mqtt_port = (uint16_t)port;
        }
        return;
    }
    if (strcmp(key, "mqtt_username") == 0) {
        strlcpy(setup->mqtt_username, value, sizeof(setup->mqtt_username));
        return;
    }
    if (strcmp(key, "mqtt_password") == 0) {
        if (value[0] != '\0') {
            strlcpy(setup->mqtt_password, value, sizeof(setup->mqtt_password));
        }
        return;
    }
    if (strcmp(key, "udp_host") == 0) {
        strlcpy(setup->udp_host, value, sizeof(setup->udp_host));
        return;
    }
    if (strcmp(key, "udp_port") == 0) {
        long port = strtol(value, NULL, 10);
        if (port > 0 && port <= 65535) {
            setup->udp_port = (uint16_t)port;
        }
        return;
    }
    if (strcmp(key, "node_id") == 0) {
        strlcpy(setup->node_id, value, sizeof(setup->node_id));
    }
}

static void parse_form_body(device_setup_config_t *setup, char *body) {
    char *cursor = body;
    while (cursor != NULL && *cursor != '\0') {
        char *pair = cursor;
        char *next = strchr(cursor, '&');
        if (next != NULL) {
            *next = '\0';
            cursor = next + 1;
        } else {
            cursor = NULL;
        }

        char *separator = strchr(pair, '=');
        if (separator == NULL) {
            continue;
        }

        *separator = '\0';
        char key[48];
        char value[128];
        url_decode(key, sizeof(key), pair);
        url_decode(value, sizeof(value), separator + 1);
        apply_form_value(setup, key, value);
    }
}

static void restart_task(void *arg) {
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(1500));
    esp_restart();
}

static esp_err_t root_get_handler(httpd_req_t *req) {
    char ssid[48];
    char password[32];
    char wifi_ssid[96];
    char mqtt_host[128];
    char mqtt_user[96];
    char udp_host[128];
    char node_id[96];
    char mode_label[48];
    char mode_description[256];
    char meta_two_label[48];
    char meta_two_value[96];
    char meta_three_label[48];
    char meta_three_value[96];
    char footer[160];
    char status_ip[48];
    char status_wifi[32];
    char status_mqtt[32];
    char status_udp[32];
    char status_uptime[32];
    char status_packets_sent[32];
    char status_packets_dropped[32];
    char status_udp_errors[32];
    char status_queue_peak[32];
    char *html = NULL;
    health_snapshot_t snapshot = health_monitor_get_snapshot();

    build_ap_identity(ssid, sizeof(ssid), password, sizeof(password));
    html_escape(wifi_ssid, sizeof(wifi_ssid), device_config_get()->wifi_ssid);
    html_escape(mqtt_host, sizeof(mqtt_host), device_config_get()->mqtt_host);
    html_escape(mqtt_user, sizeof(mqtt_user), device_config_get()->mqtt_username);
    html_escape(udp_host, sizeof(udp_host), device_config_get()->udp_host);
    html_escape(node_id, sizeof(node_id), device_config_get()->node_id);
    get_sta_ip_string(status_ip, sizeof(status_ip));
    snprintf(status_wifi,
             sizeof(status_wifi),
             "%s / %d dBm",
             snapshot.wifi_connected ? "online" : "offline",
             snapshot.wifi_rssi);
    strlcpy(status_mqtt, snapshot.mqtt_connected ? "connected" : "disconnected", sizeof(status_mqtt));
    strlcpy(status_udp, snapshot.udp_ready ? "ready" : "not ready", sizeof(status_udp));
    snprintf(status_uptime,
             sizeof(status_uptime),
             "%" PRIu32 "s",
             (uint32_t)(snapshot.uptime_ms / 1000ULL));
    snprintf(status_packets_sent, sizeof(status_packets_sent), "%" PRIu32, snapshot.packets_sent);
    snprintf(status_packets_dropped, sizeof(status_packets_dropped), "%" PRIu32, snapshot.packets_dropped);
    snprintf(status_udp_errors, sizeof(status_udp_errors), "%" PRIu32, snapshot.udp_errors);
    snprintf(status_queue_peak, sizeof(status_queue_peak), "%" PRIu32 " packets", snapshot.max_queue_fill_seen);
    if (s_mode == SETUP_PORTAL_MODE_AP) {
        strlcpy(mode_label, "ESP32-S3 Setup Portal", sizeof(mode_label));
        strlcpy(mode_description,
                "Connect this node to your home network and point it at your PC hub. After saving, the device reboots and switches into normal streaming mode.",
                sizeof(mode_description));
        strlcpy(meta_two_label, "Setup AP", sizeof(meta_two_label));
        strlcpy(meta_two_value, ssid, sizeof(meta_two_value));
        strlcpy(meta_three_label, "AP Password", sizeof(meta_three_label));
        strlcpy(meta_three_value, password, sizeof(meta_three_value));
        strlcpy(footer, "Served directly by the ESP32 setup portal at <code>http://192.168.4.1/</code>.", sizeof(footer));
    } else {
        strlcpy(mode_label, "ESP32-S3 Local Settings", sizeof(mode_label));
        strlcpy(mode_description,
                "This node is already running in station mode. You can update its network and hub settings here, then reboot into the new configuration.",
                sizeof(mode_description));
        strlcpy(meta_two_label, "Portal Mode", sizeof(meta_two_label));
        strlcpy(meta_two_value, "STA / local network", sizeof(meta_two_value));
        strlcpy(meta_three_label, "Reconfigure Action", sizeof(meta_three_label));
        strlcpy(meta_three_value, "Save and reboot", sizeof(meta_three_value));
        strlcpy(footer, "Open this page from your router-assigned device IP while the node is on your local network.", sizeof(footer));
    }

    html = calloc(1, SETUP_PORTAL_HTML_BUFFER_SIZE);
    if (html == NULL) {
        ESP_LOGE(TAG, "%s portal failed to allocate homepage buffer", portal_mode_name(s_mode));
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Out of memory");
        return ESP_ERR_NO_MEM;
    }

    int written = snprintf(
        html,
        SETUP_PORTAL_HTML_BUFFER_SIZE,
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Mic Node Setup</title>"
        "<style>"
        ":root{--bg:#f7f7f5;--card:#ffffff;--line:#e5e7eb;--text:#1f2937;--muted:#6b7280;--accent:#1f6feb;--accent-soft:#eef6ff;}"
        "*{box-sizing:border-box;}body{margin:0;padding:24px;background:radial-gradient(circle at top left,#ffffff 0%%,var(--bg) 55%%);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}"
        ".shell{max-width:840px;margin:0 auto;}.eyebrow{display:inline-block;padding:6px 10px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:13px;font-weight:700;letter-spacing:.02em;}"
        ".card{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:22px;padding:28px;box-shadow:0 18px 50px rgba(0,0,0,.06);}"
        "h1{margin:0 0 8px;font-size:30px;line-height:1.1;}.lead{margin:0;color:var(--muted);line-height:1.6;max-width:58ch;}"
        ".meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:20px 0 4px;}"
        ".meta-card{padding:16px;border-radius:16px;background:#fafaf9;border:1px solid #ececec;}.meta-card strong{display:block;margin-bottom:6px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);}"
        ".status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0 4px;}"
        ".status-card{padding:14px 16px;border-radius:16px;background:#f6fbf8;border:1px solid #dbece2;}.status-card strong{display:block;margin-bottom:6px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#5a6a60;}"
        "form{margin-top:16px;}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;}"
        "label{display:block;margin-top:14px;font-weight:700;font-size:14px;}input{width:100%%;margin-top:8px;padding:13px 14px;border:1px solid #d1d5db;border-radius:14px;font-size:15px;color:var(--text);background:#fff;}"
        ".section{margin-top:22px;padding-top:18px;border-top:1px dashed var(--line);}.section h2{margin:0 0 6px;font-size:18px;}.section p{margin:0 0 8px;color:var(--muted);line-height:1.5;}"
        "button{margin-top:24px;padding:13px 18px;border:0;border-radius:14px;background:linear-gradient(135deg,#1f6feb 0%%,#3a7cf0 100%%);color:#fff;font-size:15px;font-weight:800;letter-spacing:.01em;cursor:pointer;}"
        ".hint{margin-top:10px;color:var(--muted);font-size:14px;}.footer{margin-top:18px;color:var(--muted);font-size:13px;}"
        "</style></head><body>"
        "<div class='shell'>"
        "<span class='eyebrow'>%s</span>"
        "<div class='card'>"
        "<h1>Mic Node Setup</h1>"
        "<p class='lead'>%s</p>"
        "<div class='meta'>"
        "<div class='meta-card'><strong>Node UUID</strong><div>%s</div></div>"
        "<div class='meta-card'><strong>%s</strong><div>%s</div></div>"
        "<div class='meta-card'><strong>%s</strong><div>%s</div></div>"
        "</div>"
        "<div class='section'><h2>Current Status</h2><p>Read-only runtime information from the live node.</p>"
        "<div class='status-grid'>"
        "<div class='status-card'><strong>Current IP</strong><div>%s</div></div>"
        "<div class='status-card'><strong>Wi-Fi / RSSI</strong><div>%s</div></div>"
        "<div class='status-card'><strong>MQTT</strong><div>%s</div></div>"
        "<div class='status-card'><strong>UDP</strong><div>%s</div></div>"
        "<div class='status-card'><strong>Uptime</strong><div>%s</div></div>"
        "<div class='status-card'><strong>Packets Sent</strong><div>%s</div></div>"
        "<div class='status-card'><strong>Packets Dropped</strong><div>%s</div></div>"
        "<div class='status-card'><strong>UDP Errors</strong><div>%s</div></div>"
        "<div class='status-card'><strong>Queue Peak</strong><div>%s</div></div>"
        "</div></div>"
        "<form method='post' action='/save'>"
        "<div class='section'><h2>Wi-Fi</h2><p>These values are used for the node's normal station-mode connection.</p>"
        "<div class='grid'>"
        "<label>Wi-Fi SSID<input name='wifi_ssid' value='%s' required></label>"
        "<label>Wi-Fi Password<input type='password' name='wifi_password' value='' placeholder='Leave blank to keep existing password'></label>"
        "</div></div>"
        "<div class='section'><h2>MQTT</h2><p>The node publishes status and receives control commands through MQTT.</p>"
        "<div class='grid'>"
        "<label>MQTT Host<input name='mqtt_host' value='%s' required></label>"
        "<label>MQTT Port<input name='mqtt_port' type='number' min='1' max='65535' value='%u' required></label>"
        "<label>MQTT Username<input name='mqtt_username' value='%s'></label>"
        "<label>MQTT Password<input type='password' name='mqtt_password' value='' placeholder='Leave blank to keep existing password'></label>"
        "</div></div>"
        "<div class='section'><h2>PC Hub</h2><p>The audio stream is sent to your PC-side hub over UDP.</p>"
        "<div class='grid'>"
        "<label>UDP Host<input name='udp_host' value='%s' required></label>"
        "<label>UDP Port<input name='udp_port' type='number' min='1' max='65535' value='%u' required></label>"
        "<label>Node ID<input name='node_id' value='%s' required></label>"
        "</div></div>"
        "<button type='submit'>Save And Reboot</button>"
        "<p class='hint'>If a password field is left blank, the current saved value is kept.</p>"
        "</form>"
        "<div class='footer'>%s</div>"
        "</div></div></body></html>",
        mode_label,
        mode_description,
        device_config_get()->node_uuid,
        meta_two_label,
        meta_two_value,
        meta_three_label,
        meta_three_value,
        status_ip,
        status_wifi,
        status_mqtt,
        status_udp,
        status_uptime,
        status_packets_sent,
        status_packets_dropped,
        status_udp_errors,
        status_queue_peak,
        wifi_ssid,
        mqtt_host,
        device_config_get()->mqtt_port,
        mqtt_user,
        udp_host,
        device_config_get()->udp_port,
        node_id,
        footer);
    if (written <= 0 || (size_t)written >= SETUP_PORTAL_HTML_BUFFER_SIZE) {
        ESP_LOGE(TAG, "%s portal homepage render failed or truncated (written=%d)", portal_mode_name(s_mode), written);
        free(html);
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Portal page render failed");
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, "text/html; charset=utf-8");
    esp_err_t err = httpd_resp_send(req, html, HTTPD_RESP_USE_STRLEN);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s portal homepage send failed: %s", portal_mode_name(s_mode), esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "%s portal homepage served", portal_mode_name(s_mode));
    }
    free(html);
    return err;
}

static esp_err_t save_post_handler(httpd_req_t *req) {
    char body[1024];
    int total_len = req->content_len;
    if (total_len <= 0 || total_len >= (int)sizeof(body)) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid form payload");
        return ESP_FAIL;
    }

    int received = 0;
    while (received < total_len) {
        int ret = httpd_req_recv(req, body + received, total_len - received);
        if (ret <= 0) {
            return ESP_FAIL;
        }
        received += ret;
    }
    body[received] = '\0';

    device_setup_config_t setup = {0};
    strlcpy(setup.wifi_password, device_config_get()->wifi_password, sizeof(setup.wifi_password));
    strlcpy(setup.mqtt_password, device_config_get()->mqtt_password, sizeof(setup.mqtt_password));
    setup.mqtt_port = device_config_get()->mqtt_port;
    setup.udp_port = device_config_get()->udp_port;
    parse_form_body(&setup, body);

    device_config_actions_t actions = DEVICE_CONFIG_ACTION_NONE;
    esp_err_t err = device_config_commit_setup(&setup, &actions);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save setup: %s", esp_err_to_name(err));
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Failed to save configuration");
        return err;
    }

    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_sendstr(req,
                       "<!doctype html><html><body style='font-family:sans-serif;padding:24px;'>"
                       "<h1>Configuration saved ✨</h1>"
                       "<p>The device will reboot in a moment and try to join your Wi-Fi network.</p>"
                       "</body></html>");

    xTaskCreate(restart_task, "setup_restart", 2048, NULL, 3, NULL);
    return ESP_OK;
}

static esp_err_t start_http_server(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.lru_purge_enable = true;
    // Keep the portal conservative on lwIP socket usage so STA-mode startup
    // does not fail on small default socket limits.
    config.max_open_sockets = 2;

    esp_err_t err = httpd_start(&s_http_server, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s portal httpd_start failed: %s", portal_mode_name(s_mode), esp_err_to_name(err));
        return err;
    }

    httpd_uri_t root = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = root_get_handler,
    };
    httpd_uri_t save = {
        .uri = "/save",
        .method = HTTP_POST,
        .handler = save_post_handler,
    };

    err = httpd_register_uri_handler(s_http_server, &root);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s portal root handler registration failed: %s", portal_mode_name(s_mode), esp_err_to_name(err));
        httpd_stop(s_http_server);
        s_http_server = NULL;
        return err;
    }

    err = httpd_register_uri_handler(s_http_server, &save);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s portal save handler registration failed: %s", portal_mode_name(s_mode), esp_err_to_name(err));
        httpd_stop(s_http_server);
        s_http_server = NULL;
        return err;
    }
    ESP_LOGI(TAG, "%s portal HTTP server started on port %u", portal_mode_name(s_mode), (unsigned)config.server_port);
    return ESP_OK;
}

esp_err_t setup_portal_start(setup_portal_mode_t mode) {
    s_mode = mode;

    if (s_http_server != NULL) {
        ESP_LOGW(TAG, "HTTP portal already running");
        return ESP_OK;
    }

    if (mode == SETUP_PORTAL_MODE_STA) {
        ESP_LOGI(TAG, "Starting local reconfiguration portal on STA interface");
        esp_err_t err = start_http_server();
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "STA portal started on local network interface");
        }
        return err;
    }

    char ssid[48];
    char password[32];
    build_ap_identity(ssid, sizeof(ssid), password, sizeof(password));

    esp_netif_create_default_wifi_ap();

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.ap.ssid, ssid, sizeof(wifi_config.ap.ssid));
    strlcpy((char *)wifi_config.ap.password, password, sizeof(wifi_config.ap.password));
    wifi_config.ap.ssid_len = strlen(ssid);
    wifi_config.ap.max_connection = 4;
    wifi_config.ap.channel = 6;
    wifi_config.ap.authmode = WIFI_AUTH_WPA_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGW(TAG, "Setup portal active on SSID=%s password=%s", ssid, password);
    ESP_LOGW(TAG, "Open http://192.168.4.1/ to configure the device");

    esp_err_t err = start_http_server();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "AP portal ready on http://192.168.4.1/");
    }
    return err;
}
