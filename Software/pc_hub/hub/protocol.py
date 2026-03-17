from __future__ import annotations

import struct

from hub.models import AudioFrame


AUDIO_PACKET_MAGIC = 0x41554430
AUDIO_PACKET_VERSION = 1
NODE_UUID_LEN = 32
NODE_ID_LEN = 32
HEADER_STRUCT = struct.Struct("<IB32s32sIQHBBH")


def parse_audio_packet(data: bytes, arrival_time: float) -> AudioFrame:
    if len(data) < HEADER_STRUCT.size:
        raise ValueError("packet too short")

    unpacked = HEADER_STRUCT.unpack_from(data)
    (
        magic,
        version,
        node_uuid_raw,
        node_id_raw,
        seq,
        timestamp_us,
        sample_rate,
        channels,
        bits_per_sample,
        payload_bytes,
    ) = unpacked

    if magic != AUDIO_PACKET_MAGIC:
        raise ValueError(f"unexpected magic: {magic:#x}")
    if version != AUDIO_PACKET_VERSION:
        raise ValueError(f"unexpected version: {version}")

    payload = data[HEADER_STRUCT.size:]
    if len(payload) != payload_bytes:
        raise ValueError("payload length mismatch")

    return AudioFrame(
        node_uuid=_decode_fixed_string(node_uuid_raw),
        node_id=_decode_fixed_string(node_id_raw),
        seq=seq,
        timestamp_us=timestamp_us,
        sample_rate=sample_rate,
        channels=channels,
        bits_per_sample=bits_per_sample,
        payload_bytes=payload_bytes,
        samples=payload,
        arrival_time=arrival_time,
    )


def _decode_fixed_string(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
