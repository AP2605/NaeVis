"""Binary Camera Frame Packet Protocol Specification.

Binary Packet Layout (20-byte Header + JPEG Payload):
======================================================
Offset  Size (Bytes)  Type      Field Name     Description
-----------------------------------------------------------------------------
0       4             char[4]   magic          Protocol magic bytes ("NAVC")
4       4             uint32    frame_id       Monotonically increasing frame index (Big-Endian)
8       8             float64   timestamp      POSIX timestamp in seconds (Big-Endian double)
16      4             uint32    payload_size   Byte length of subsequent JPEG payload (Big-Endian)
20      N             bytes     jpeg_bytes     Standard JPEG image data (SOI: 0xFFD8 ... EOI: 0xFFD9)

Total Packet Size = 20 + payload_size bytes.

This fixed-size header enables zero-copy streaming, high-throughput binary transport,
and direct metadata parsing by SLAM algorithms and video display pipelines without
JSON/Base64 encoding overhead.
"""

import struct
import time
from typing import Tuple

# Protocol Constants
CAMERA_PACKET_MAGIC = b"NAVC"
HEADER_SIZE_BYTES = 20
HEADER_STRUCT_FORMAT = ">4sIdI"  # (magic: 4s, frame_id: I, timestamp: d, payload_size: I)
MAX_ALLOWED_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB maximum frame size safeguard
MIN_JPEG_SIZE_BYTES = 4


def encode_camera_packet(frame_id: int, timestamp: float, jpeg_bytes: bytes) -> bytes:
    """Encode metadata and raw JPEG bytes into a standard 20-byte header binary packet.

    Args:
        frame_id: Monotonically increasing frame identifier.
        timestamp: Capture timestamp in seconds (float64).
        jpeg_bytes: Raw JPEG image payload.

    Returns:
        bytes: Packed binary message containing [20-byte header][JPEG payload].
    """
    payload_size = len(jpeg_bytes)
    if payload_size > MAX_ALLOWED_FRAME_SIZE:
        raise ValueError(
            f"JPEG payload size ({payload_size} bytes) exceeds maximum allowable limit ({MAX_ALLOWED_FRAME_SIZE} bytes)"
        )

    header = struct.pack(
        HEADER_STRUCT_FORMAT,
        CAMERA_PACKET_MAGIC,
        frame_id & 0xFFFFFFFF,
        float(timestamp),
        payload_size,
    )
    return header + jpeg_bytes


def decode_camera_packet(data: bytes) -> Tuple[int, float, bytes]:
    """Decode and validate a binary camera packet or raw JPEG stream.

    Supports:
    1. Standard NAVC binary packets: [20-byte header][JPEG payload]
    2. Raw JPEG image bytes: (starts with 0xFFD8), automatically assigned fallback metadata.

    Args:
        data: Incoming binary WebSocket message.

    Returns:
        tuple[int, float, bytes]: (frame_id, timestamp, jpeg_bytes)

    Raises:
        ValueError: If packet header is malformed, magic is invalid, or payload size is invalid.
    """
    if not data or len(data) < MIN_JPEG_SIZE_BYTES:
        raise ValueError(f"Packet too short to process ({len(data)} bytes)")

    if len(data) > (HEADER_SIZE_BYTES + MAX_ALLOWED_FRAME_SIZE):
        raise ValueError(f"Packet size ({len(data)} bytes) exceeds maximum limit")

    # 1. Check for standard 20-byte NAVC header
    if len(data) >= HEADER_SIZE_BYTES and data[:4] == CAMERA_PACKET_MAGIC:
        try:
            magic, frame_id, timestamp, payload_size = struct.unpack(
                HEADER_STRUCT_FORMAT, data[:HEADER_SIZE_BYTES]
            )
        except struct.error as err:
            raise ValueError(f"Corrupted binary header: {err}") from err

        if payload_size > MAX_ALLOWED_FRAME_SIZE:
            raise ValueError(
                f"Header declared payload size {payload_size} exceeds safety limit {MAX_ALLOWED_FRAME_SIZE}"
            )

        actual_payload_len = len(data) - HEADER_SIZE_BYTES
        if actual_payload_len < payload_size:
            raise ValueError(
                f"Truncated packet: expected {payload_size} payload bytes, received {actual_payload_len}"
            )

        jpeg_bytes = data[HEADER_SIZE_BYTES : HEADER_SIZE_BYTES + payload_size]
        return frame_id, float(timestamp), jpeg_bytes

    # 2. Backward compatibility: Raw JPEG frame (starts with standard JPEG SOI: 0xFF, 0xD8)
    if data[:2] == b"\xff\xd8":
        # Assign current timestamp and default frame_id 0 (auto-incremented by service)
        return 0, time.time(), data

    raise ValueError("Invalid packet format: missing NAVC magic header and valid JPEG SOI marker")
