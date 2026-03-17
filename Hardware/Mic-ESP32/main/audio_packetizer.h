#pragma once

#include <stddef.h>
#include <stdint.h>

#include "audio_protocol.h"

void audio_packetizer_prepare(audio_packet_t *packet,
                              const char *node_uuid,
                              const char *node_id,
                              uint32_t seq,
                              uint64_t timestamp_us,
                              const int16_t *samples,
                              size_t sample_count);
