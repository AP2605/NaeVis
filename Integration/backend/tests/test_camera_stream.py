"""Tests for WebSocket Camera binary streaming."""

from fastapi.testclient import TestClient
from app.main import app
from app.services.camera_service import camera_service

client = TestClient(app)


def test_camera_websocket_viewer_and_producer():
    """Test producer sending binary image bytes and viewer receiving them."""
    fake_jpeg_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xd9"

    # Connect viewer
    with client.websocket_connect("/ws/camera?role=viewer") as ws_viewer:
        # Connect producer in parallel
        with client.websocket_connect("/ws/camera?role=producer") as ws_producer:
            # Send binary bytes from producer
            ws_producer.send_bytes(fake_jpeg_frame)

            # Receive bytes on viewer
            received = ws_viewer.receive_bytes()
            assert received == fake_jpeg_frame


def test_camera_stats_endpoint():
    """Test GET /api/v1/integration/camera/stats returns valid metrics."""
    resp = client.get("/api/v1/integration/camera/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert "fps" in stats
    assert "total_frames" in stats
    assert "viewers" in stats
    assert "has_frame" in stats


def test_camera_viewer_disconnect_cleanup():
    """Test that viewer count decrements upon disconnection."""
    initial_viewers = camera_service.viewer_count
    with client.websocket_connect("/ws/camera?role=viewer") as ws:
        assert camera_service.viewer_count == initial_viewers + 1
    # After exiting context, viewer is unregistered
    assert camera_service.viewer_count == initial_viewers
