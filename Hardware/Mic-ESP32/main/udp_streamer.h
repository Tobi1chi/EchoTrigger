#pragma once

#include <stdbool.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

esp_err_t udp_streamer_init(QueueHandle_t packet_queue);
esp_err_t udp_streamer_reconfigure_target(void);
void udp_streamer_set_network_ready(bool ready);
