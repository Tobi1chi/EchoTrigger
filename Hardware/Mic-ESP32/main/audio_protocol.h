#pragma once

#include <stdint.h>

#define AUDIO_PACKET_MAGIC 0x41554430UL
#define AUDIO_PACKET_VERSION 1U
#define AUDIO_SAMPLE_RATE_HZ 16000U
#define AUDIO_BITS_PER_SAMPLE 16U
#define AUDIO_CHANNEL_COUNT 1U
#define AUDIO_PACKET_DURATION_MS 20U
#define AUDIO_SAMPLES_PER_PACKET ((AUDIO_SAMPLE_RATE_HZ * AUDIO_PACKET_DURATION_MS) / 1000U)
#define AUDIO_PAYLOAD_BYTES (AUDIO_SAMPLES_PER_PACKET * sizeof(int16_t))
#define AUDIO_NODE_UUID_MAX_LEN 32
#define AUDIO_NODE_ID_MAX_LEN 32

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint8_t version;
    char node_uuid[AUDIO_NODE_UUID_MAX_LEN];
    char node_id[AUDIO_NODE_ID_MAX_LEN];
    uint32_t seq;
    uint64_t timestamp_us;
    uint16_t sample_rate;
    uint8_t channels;
    uint8_t bits_per_sample;
    uint16_t payload_bytes;
} audio_packet_header_t;

typedef struct {
    audio_packet_header_t header;
    int16_t samples[AUDIO_SAMPLES_PER_PACKET];
} audio_packet_t;
