#include "audio_packetizer.h"

#include <string.h>

void audio_packetizer_prepare(audio_packet_t *packet,
                              const char *node_uuid,
                              const char *node_id,
                              uint32_t seq,
                              uint64_t timestamp_us,
                              const int16_t *samples,
                              size_t sample_count) {
    memset(packet, 0, sizeof(*packet));
    packet->header.magic = AUDIO_PACKET_MAGIC;
    packet->header.version = AUDIO_PACKET_VERSION;
    strncpy(packet->header.node_uuid, node_uuid, sizeof(packet->header.node_uuid) - 1U);
    strncpy(packet->header.node_id, node_id, sizeof(packet->header.node_id) - 1U);
    packet->header.seq = seq;
    packet->header.timestamp_us = timestamp_us;
    packet->header.sample_rate = AUDIO_SAMPLE_RATE_HZ;
    packet->header.channels = AUDIO_CHANNEL_COUNT;
    packet->header.bits_per_sample = AUDIO_BITS_PER_SAMPLE;
    packet->header.payload_bytes = (uint16_t)(sample_count * sizeof(int16_t));
    memcpy(packet->samples, samples, packet->header.payload_bytes);
}
