#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

esp_err_t audio_capture_init(QueueHandle_t packet_queue);
void audio_capture_set_streaming_enabled(bool enabled);
TaskHandle_t audio_capture_get_task_handle(void);
