#include "udp_streamer.h"

#include <arpa/inet.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#include "audio_protocol.h"
#include "device_config.h"
#include "esp_log.h"
#include "freertos/task.h"
#include "health_monitor.h"
#include "lwip/netdb.h"

static const char *TAG = "udp_streamer";
static StaticTask_t s_udp_task_buffer;
static StackType_t s_udp_task_stack[4096];
static TaskHandle_t s_udp_task_handle;
static QueueHandle_t s_packet_queue;
static int s_socket_fd = -1;
static struct sockaddr_in s_remote_addr;
static volatile bool s_network_ready;

static esp_err_t resolve_remote(void) {
    const device_config_t *config = device_config_get();

    struct addrinfo hints = {
        .ai_family = AF_INET,
        .ai_socktype = SOCK_DGRAM,
    };
    struct addrinfo *result = NULL;

    char port_str[8];
    snprintf(port_str, sizeof(port_str), "%u", config->udp_port);

    int err = getaddrinfo(config->udp_host, port_str, &hints, &result);
    if (err != 0 || result == NULL) {
        ESP_LOGE(TAG, "getaddrinfo failed for %s:%s", config->udp_host, port_str);
        return ESP_FAIL;
    }

    memcpy(&s_remote_addr, result->ai_addr, sizeof(struct sockaddr_in));
    freeaddrinfo(result);
    return ESP_OK;
}

static esp_err_t open_socket(void) {
    if (s_socket_fd >= 0) {
        close(s_socket_fd);
        s_socket_fd = -1;
    }

    esp_err_t err = resolve_remote();
    if (err != ESP_OK) {
        health_monitor_set_udp_ready(false);
        return err;
    }

    s_socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (s_socket_fd < 0) {
        ESP_LOGE(TAG, "socket create failed: errno=%d", errno);
        health_monitor_set_udp_ready(false);
        return ESP_FAIL;
    }

    health_monitor_set_udp_ready(true);
    return ESP_OK;
}

static void udp_task(void *arg) {
    (void)arg;

    audio_packet_t packet;

    while (true) {
        if (!s_network_ready) {
            vTaskDelay(pdMS_TO_TICKS(250));
            continue;
        }

        if (s_socket_fd < 0 && open_socket() != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        if (xQueueReceive(s_packet_queue, &packet, pdMS_TO_TICKS(250)) != pdTRUE) {
            continue;
        }

        ssize_t sent = sendto(s_socket_fd,
                              &packet,
                              sizeof(packet.header) + packet.header.payload_bytes,
                              0,
                              (struct sockaddr *)&s_remote_addr,
                              sizeof(s_remote_addr));
        if (sent < 0) {
            ESP_LOGW(TAG, "sendto failed: errno=%d", errno);
            health_monitor_increment_udp_errors();
            health_monitor_set_udp_ready(false);
            close(s_socket_fd);
            s_socket_fd = -1;
            continue;
        }

        health_monitor_increment_packets_sent();
    }
}

esp_err_t udp_streamer_init(QueueHandle_t packet_queue) {
    s_packet_queue = packet_queue;
    s_udp_task_handle = xTaskCreateStaticPinnedToCore(udp_task,
                                                      "udp_task",
                                                      sizeof(s_udp_task_stack) / sizeof(StackType_t),
                                                      NULL,
                                                      configMAX_PRIORITIES - 3,
                                                      s_udp_task_stack,
                                                      &s_udp_task_buffer,
                                                      tskNO_AFFINITY);
    return s_udp_task_handle == NULL ? ESP_ERR_NO_MEM : ESP_OK;
}

esp_err_t udp_streamer_reconfigure_target(void) {
    return open_socket();
}

void udp_streamer_set_network_ready(bool ready) {
    s_network_ready = ready;
    if (!ready) {
        health_monitor_set_udp_ready(false);
        if (s_socket_fd >= 0) {
            close(s_socket_fd);
            s_socket_fd = -1;
        }
    }
}
