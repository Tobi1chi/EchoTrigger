#pragma once

#include <stdbool.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

esp_err_t udp_streamer_init(QueueHandle_t packet_queue);
esp_err_t udp_streamer_reconfigure_target(void);
void udp_streamer_set_network_ready(bool ready);
TaskHandle_t udp_streamer_get_task_handle(void);
