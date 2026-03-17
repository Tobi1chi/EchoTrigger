#include "audio_capture.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "audio_packetizer.h"
#include "audio_protocol.h"
#include "device_config.h"
#include "driver/i2s_std.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include "health_monitor.h"

static const char *TAG = "audio_capture";
static StackType_t s_audio_task_stack[4096];
static StaticTask_t s_audio_task_buffer;
static TaskHandle_t s_audio_task_handle;
static QueueHandle_t s_packet_queue;
static i2s_chan_handle_t s_i2s_rx_handle;
static volatile bool s_streaming_enabled;
static uint32_t s_sequence;

static void audio_task(void *arg) {
    (void)arg;

    int32_t raw_samples[AUDIO_SAMPLES_PER_PACKET];
    int16_t pcm_samples[AUDIO_SAMPLES_PER_PACKET];
    audio_packet_t packet;

    while (true) {
        if (!s_streaming_enabled) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        size_t bytes_read = 0;
        esp_err_t err = i2s_channel_read(s_i2s_rx_handle,
                                         raw_samples,
                                         sizeof(raw_samples),
                                         &bytes_read,
                                         portMAX_DELAY);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "i2s read failed: %s", esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        size_t sample_count = bytes_read / sizeof(int32_t);
        if (sample_count < AUDIO_SAMPLES_PER_PACKET) {
            continue;
        }

        for (size_t i = 0; i < AUDIO_SAMPLES_PER_PACKET; ++i) {
            pcm_samples[i] = (int16_t)(raw_samples[i] >> 14);
        }

        audio_packetizer_prepare(&packet,
                                 device_config_get()->node_uuid,
                                 device_config_get()->node_id,
                                 s_sequence++,
                                 (uint64_t)esp_timer_get_time(),
                                 pcm_samples,
                                 AUDIO_SAMPLES_PER_PACKET);

        if (xQueueSendToBack(s_packet_queue, &packet, 0) != pdTRUE) {
            audio_packet_t dropped;
            if (xQueueReceive(s_packet_queue, &dropped, 0) == pdTRUE &&
                xQueueSendToBack(s_packet_queue, &packet, 0) == pdTRUE) {
                health_monitor_increment_packets_dropped();
            } else {
                health_monitor_increment_packets_dropped();
            }
        }
    }
}

esp_err_t audio_capture_init(QueueHandle_t packet_queue) {
    const device_config_t *config = device_config_get();
    s_packet_queue = packet_queue;
    s_streaming_enabled = config->streaming_enabled;

    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &s_i2s_rx_handle);
    if (err != ESP_OK) {
        return err;
    }

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE_HZ),
        .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = config->i2s_bclk_pin,
            .ws = config->i2s_ws_pin,
            .dout = I2S_GPIO_UNUSED,
            .din = config->i2s_din_pin,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };

    err = i2s_channel_init_std_mode(s_i2s_rx_handle, &std_cfg);
    if (err != ESP_OK) {
        return err;
    }

    err = i2s_channel_enable(s_i2s_rx_handle);
    if (err != ESP_OK) {
        return err;
    }

    s_audio_task_handle = xTaskCreateStaticPinnedToCore(audio_task,
                                                        "audio_task",
                                                        sizeof(s_audio_task_stack) / sizeof(StackType_t),
                                                        NULL,
                                                        configMAX_PRIORITIES - 2,
                                                        s_audio_task_stack,
                                                        &s_audio_task_buffer,
                                                        tskNO_AFFINITY);
    return s_audio_task_handle == NULL ? ESP_ERR_NO_MEM : ESP_OK;
}

void audio_capture_set_streaming_enabled(bool enabled) {
    s_streaming_enabled = enabled;
    health_monitor_set_streaming_enabled(enabled);
}
