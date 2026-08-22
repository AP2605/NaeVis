"""Comprehensive Tests for Multi-Consumer Binary Camera Streaming, Real P2 Ingestion, and SLAM Bridge.

Validates:
1. Binary packet encoding and 20-byte NAVC header parsing.
2. Raw JPEG bytes ingestion from real P2 Blender without structured header.
3. /ws/video endpoint receiving raw JPEG from P2 and streaming to frontend live camera.
4. P2 connect, disconnect, and reconnect lifecycles without server crash.
5. Frame ID and timestamp preservation across distribution channels.
6. /ws/slam endpoint delivering binary packets to SLAM consumers.
7. /ws/camera endpoint supporting both legacy viewers and producers.
8. Multi-consumer fan-out: single frame broadcasted simultaneously to all channels.
9. Fault-tolerance: disconnected consumer does not break or block active consumers.
10. Malformed and empty packet rejection.
11. In-process SLAM subscription hooks.
12. Camera diagnostic stats reporting across all consumer types.
"""

import pytest
import time
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.camera_packet import (
    CAMERA_PACKET_MAGIC,
    HEADER_SIZE_BYTES,
    decode_camera_packet,
    encode_camera_packet,
)
from app.services.camera_service import camera_service

client = TestClient(app)

# Standard mock JPEG frame bytes (valid SOI 0xFFD8 ... EOI 0xFFD9)
SAMPLE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xd9"
)


@pytest.fixture(autouse=True)
def reset_camera_state():
    """Ensure clean camera service state before and after each test."""
    camera_service.reset()
    yield
    camera_service.reset()


# =============================================================================
# 1. CODEC & BINARY PROTOCOL TESTS
# =============================================================================

def test_camera_packet_encode_decode_roundtrip():
    """Test 20-byte NAVC header binary encoding and decoding roundtrip."""
    frame_id = 42
    timestamp = 1724284800.123456
    encoded = encode_camera_packet(frame_id, timestamp, SAMPLE_JPEG_BYTES)

    assert len(encoded) == HEADER_SIZE_BYTES + len(SAMPLE_JPEG_BYTES)
    assert encoded[:4] == CAMERA_PACKET_MAGIC

    dec_frame_id, dec_ts, dec_jpeg = decode_camera_packet(encoded)
    assert dec_frame_id == frame_id
    assert abs(dec_ts - timestamp) < 1e-5
    assert dec_jpeg == SAMPLE_JPEG_BYTES


def test_decode_raw_jpeg_backward_compatibility():
    """Verify that pure raw JPEG frames without binary header are decoded safely."""
    dec_frame_id, dec_ts, dec_jpeg = decode_camera_packet(SAMPLE_JPEG_BYTES)
    assert dec_jpeg == SAMPLE_JPEG_BYTES
    assert dec_ts > 0


def test_malformed_packets_rejected_safely():
    """Verify corrupted, truncated, or invalid magic packets are rejected."""
    # 1. Invalid magic
    corrupted_magic = b"UNKN" + b"\x00" * 16 + SAMPLE_JPEG_BYTES
    try:
        decode_camera_packet(corrupted_magic)
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        assert "Invalid packet format" in str(exc)

    # 2. Truncated packet
    truncated = encode_camera_packet(1, time.time(), SAMPLE_JPEG_BYTES)[:-5]
    try:
        decode_camera_packet(truncated)
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        assert "Truncated packet" in str(exc) or "too short" in str(exc)

    # 3. Oversized payload declaration
    try:
        encode_camera_packet(1, time.time(), b"\x00" * (11 * 1024 * 1024))
        assert False, "Should have raised ValueError for >10MB"
    except ValueError as exc:
        assert "exceeds maximum allowable limit" in str(exc)


# =============================================================================
# 2. REAL P2 RAW JPEG INGESTION & /ws/video ENDPOINT TESTS
# =============================================================================

def test_real_p2_raw_jpeg_stream_to_video_endpoint():
    """Test Real P2 Blender connecting to /ws/video and streaming RAW JPEG bytes."""
    # Connect frontend viewer to /ws/video
    with client.websocket_connect("/ws/video") as ws_frontend:
        # P2 connects directly to /ws/video (with or without role param)
        with client.websocket_connect("/ws/video") as ws_p2_blender:
            # P2 sends pure raw JPEG bytes (starts with \xff\xd8)
            ws_p2_blender.send_bytes(SAMPLE_JPEG_BYTES)

            # Frontend receives the frame packet
            received = ws_frontend.receive_bytes()
            assert len(received) >= len(SAMPLE_JPEG_BYTES)
            f_id, ts, jpeg = decode_camera_packet(received)
            assert f_id >= 1
            assert ts > 0
            assert jpeg == SAMPLE_JPEG_BYTES
            assert camera_service.get_latest_frame() == SAMPLE_JPEG_BYTES


def test_p2_reconnect_lifecycle():
    """Test P2 connecting, sending frames, disconnecting, and reconnecting seamlessly."""
    with client.websocket_connect("/ws/video") as ws_frontend:
        # First P2 session
        with client.websocket_connect("/ws/video?role=producer") as ws_p2_1:
            ws_p2_1.send_bytes(SAMPLE_JPEG_BYTES)
            rec1 = ws_frontend.receive_bytes()
            _, _, jpeg1 = decode_camera_packet(rec1)
            assert jpeg1 == SAMPLE_JPEG_BYTES

        # P2 disconnects (session 1 closed)

        # Second P2 session (reconnected)
        with client.websocket_connect("/ws/video?role=producer") as ws_p2_2:
            ws_p2_2.send_bytes(SAMPLE_JPEG_BYTES)
            rec2 = ws_frontend.receive_bytes()
            _, _, jpeg2 = decode_camera_packet(rec2)
            assert jpeg2 == SAMPLE_JPEG_BYTES


def test_empty_and_malformed_frames_handled_gracefully():
    """Verify empty or non-JPEG frames to /ws/video do not crash the server."""
    with client.websocket_connect("/ws/video") as ws_frontend:
        with client.websocket_connect("/ws/video?role=producer") as ws_producer:
            # Send invalid non-JPEG bytes
            ws_producer.send_bytes(b"INVALID_NOT_JPEG_BYTES")
            # Then send valid JPEG
            ws_producer.send_bytes(SAMPLE_JPEG_BYTES)

            rec = ws_frontend.receive_bytes()
            _, _, jpeg = decode_camera_packet(rec)
            assert jpeg == SAMPLE_JPEG_BYTES


# =============================================================================
# 3. WEBSOCKET ENDPOINTS & MULTI-CHANNEL DISTRIBUTION TESTS
# =============================================================================

def test_ws_camera_producer_and_viewer():
    """Test legacy /ws/camera endpoint with producer and viewer roles."""
    with client.websocket_connect("/ws/camera?role=viewer") as ws_viewer:
        with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
            packet = encode_camera_packet(101, 12.34, SAMPLE_JPEG_BYTES)
            ws_producer.send_bytes(packet)

            received = ws_viewer.receive_bytes()
            assert received == SAMPLE_JPEG_BYTES


def test_ws_slam_endpoint_receives_structured_binary_packet():
    """Test /ws/slam endpoint receives structured [20-byte header + JPEG] packet."""
    with client.websocket_connect("/ws/slam") as ws_slam:
        with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
            target_frame_id = 777
            target_ts = 123.456
            packet = encode_camera_packet(target_frame_id, target_ts, SAMPLE_JPEG_BYTES)
            ws_producer.send_bytes(packet)

            received = ws_slam.receive_bytes()
            assert len(received) == len(packet)
            f_id, ts, jpeg = decode_camera_packet(received)
            assert f_id == target_frame_id
            assert abs(ts - target_ts) < 1e-4
            assert jpeg == SAMPLE_JPEG_BYTES


def test_single_blender_frame_fanout_to_all_consumers():
    """Verify a SINGLE producer frame is distributed to /ws/camera, /ws/slam, and /ws/video simultaneously."""
    frame_id = 999
    ts = 888.123
    single_frame_packet = encode_camera_packet(frame_id, ts, SAMPLE_JPEG_BYTES)

    with client.websocket_connect("/ws/camera?role=viewer") as ws_cam_viewer:
        with client.websocket_connect("/ws/slam") as ws_slam:
            with client.websocket_connect("/ws/video") as ws_video:
                with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
                    ws_producer.send_bytes(single_frame_packet)

                    # 1. /ws/camera viewer receives raw JPEG
                    cam_rec = ws_cam_viewer.receive_bytes()
                    assert cam_rec == SAMPLE_JPEG_BYTES

                    # 2. /ws/slam consumer receives full packet with matching metadata
                    slam_rec = ws_slam.receive_bytes()
                    s_id, s_ts, s_jpeg = decode_camera_packet(slam_rec)
                    assert s_id == frame_id
                    assert abs(s_ts - ts) < 1e-4
                    assert s_jpeg == SAMPLE_JPEG_BYTES

                    # 3. /ws/video consumer receives full packet with matching metadata
                    vid_rec = ws_video.receive_bytes()
                    v_id, v_ts, v_jpeg = decode_camera_packet(vid_rec)
                    assert v_id == frame_id
                    assert abs(v_ts - ts) < 1e-4
                    assert v_jpeg == SAMPLE_JPEG_BYTES


def test_disconnected_consumer_does_not_break_other_streams():
    """Verify that disconnecting one consumer channel does not crash or block remaining consumers."""
    packet_1 = encode_camera_packet(1, 1.0, SAMPLE_JPEG_BYTES)
    packet_2 = encode_camera_packet(2, 2.0, SAMPLE_JPEG_BYTES)

    with client.websocket_connect("/ws/video") as ws_video:
        # Connect temporary SLAM consumer and disconnect it
        with client.websocket_connect("/ws/slam") as ws_slam:
            with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
                ws_producer.send_bytes(packet_1)
                _ = ws_slam.receive_bytes()
                _ = ws_video.receive_bytes()

        # ws_slam is now closed/disconnected. Send next frame
        with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
            ws_producer.send_bytes(packet_2)

            rec2 = ws_video.receive_bytes()
            f_id, _, jpeg = decode_camera_packet(rec2)
            assert f_id == 2
            assert jpeg == SAMPLE_JPEG_BYTES


def test_in_process_slam_callback_hook():
    """Test in-process SLAM subscription hook receives frame_id, timestamp, and JPEG."""
    received_frames = []

    def my_slam_hook(f_id: int, timestamp: float, jpeg_bytes: bytes):
        received_frames.append((f_id, timestamp, jpeg_bytes))

    camera_service.register_slam_callback(my_slam_hook)
    try:
        test_pkt = encode_camera_packet(505, 99.9, SAMPLE_JPEG_BYTES)
        with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
            ws_producer.send_bytes(test_pkt)

        time.sleep(0.05)
        assert len(received_frames) >= 1
        assert received_frames[-1][0] == 505
        assert received_frames[-1][2] == SAMPLE_JPEG_BYTES
    finally:
        camera_service.unregister_slam_callback(my_slam_hook)


def test_camera_stats_endpoint_multi_channel():
    """Test GET /api/v1/integration/camera/stats reflects all viewer types."""
    resp = client.get("/api/v1/integration/camera/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert "fps" in stats
    assert "total_frames" in stats
    assert "viewers" in stats
    assert "slam_consumers" in stats
    assert "video_consumers" in stats
    assert "producers" in stats
    assert "has_frame" in stats
