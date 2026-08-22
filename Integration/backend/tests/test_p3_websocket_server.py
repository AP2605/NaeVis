"""Unit and Integration tests for Dedicated P3 Navigation WebSocket Server (Port 8004)."""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app as main_app
from app.websocket.navigation_server import nav_app
from app.services.frame_sync import frame_synchronizer
from app.services.camera_service import camera_service
from app.repositories.trajectory_repository import trajectory_repository

nav_client = TestClient(nav_app)
main_client = TestClient(main_app)


@pytest.fixture(autouse=True)
def reset_services():
    """Reset shared buffers and services before each test."""
    frame_synchronizer.reset()
    camera_service.reset()
    trajectory_repository.clear()
    yield
    frame_synchronizer.reset()
    camera_service.reset()
    trajectory_repository.clear()


def test_navigation_server_health_and_root():
    """Verify HTTP endpoints on the navigation WebSocket server."""
    health_resp = nav_client.get("/health")
    assert health_resp.status_code == 200
    data = health_resp.json()
    assert data["status"] == "online"
    assert data["port"] == 8004

    root_resp = nav_client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert root_data["service"] == "P3 Navigation Receiver"


def test_navigation_websocket_valid_real_packet():
    """Verify valid P3 navigation packet ingestion over WebSocket preserves frame_id, timestamp, and sets REAL status."""
    valid_payload = {
        "frame_id": 125,
        "timestamp": 4.166,
        "estimated_pose": {
            "x": 10.42,
            "y": 5.81,
            "z": 20.13,
            "roll": 0.3,
            "pitch": -1.1,
            "yaw": 89.7,
        },
        "velocity": {
            "x": 3.2,
            "y": 0.0,
            "z": 0.1,
        },
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.96,
        "processing_time_ms": 0.4,
    }

    with nav_client.websocket_connect("/ws/navigation?source=real") as ws:
        ws.send_text(json.dumps(valid_payload))

        # Verify frame synchronizer updated with exact values
        assert frame_synchronizer._latest_p3 is not None
        assert frame_synchronizer._latest_p3.frame_id == 125
        assert frame_synchronizer._latest_p3.timestamp == 4.166
        assert frame_synchronizer._latest_p3.estimated_pose.x == 10.42
        assert frame_synchronizer._latest_p3.confidence == 0.96

        # Verify source health indicates CONNECTED and is_real=True
        health = frame_synchronizer.get_source_health()
        assert health["p3"]["state"] == "CONNECTED"
        assert health["p3"]["is_real"] is True
        assert health["p3"]["last_frame_id"] == 125

        # Verify trajectory repository recorded estimated pose
        traj = trajectory_repository.get_trajectory(limit=10)
        assert len(traj.estimated) == 1
        assert traj.estimated[0].frame_id == 125
        assert traj.estimated[0].x == 10.42


def test_navigation_websocket_mock_provenance():
    """Verify ?source=mock records as MOCK in source health."""
    payload = {
        "frame_id": 10,
        "timestamp": 0.5,
        "estimated_pose": {"x": 1.0, "y": 2.0, "z": 10.0},
    }

    with nav_client.websocket_connect("/ws/navigation?source=mock") as ws:
        ws.send_text(json.dumps(payload))

        health = frame_synchronizer.get_source_health()
        assert health["p3"]["state"] == "MOCK"
        assert health["p3"]["is_real"] is False


def test_navigation_websocket_invalid_json_resilience():
    """Verify invalid JSON does not crash the server and subsequent valid packet is ingested."""
    with nav_client.websocket_connect("/ws/navigation?source=real") as ws:
        # 1. Send malformed JSON string
        ws.send_text("{invalid json payload content...")
        err_msg = ws.receive_json()
        assert err_msg["status"] == "error"
        assert err_msg["code"] == "INVALID_JSON"

        # 2. Server remains alive, send valid packet
        valid = {
            "frame_id": 20,
            "timestamp": 1.0,
            "estimated_pose": {"x": 5.0, "y": 6.0, "z": 12.0},
        }
        ws.send_text(json.dumps(valid))

        assert frame_synchronizer._latest_p3 is not None
        assert frame_synchronizer._latest_p3.frame_id == 20
        assert frame_synchronizer._latest_p3.estimated_pose.x == 5.0


def test_navigation_websocket_schema_validation_failure_resilience():
    """Verify packet with missing required estimated_pose is rejected without corrupting state."""
    with nav_client.websocket_connect("/ws/navigation?source=real") as ws:
        # 1. Missing required estimated_pose
        invalid_schema = {"frame_id": 30, "timestamp": 1.5, "velocity": {"x": 1.0, "y": 0.0, "z": 0.0}}
        ws.send_text(json.dumps(invalid_schema))
        err_msg = ws.receive_json()
        assert err_msg["status"] == "error"
        assert err_msg["code"] == "VALIDATION_FAILED"

        # 2. Send valid packet
        valid = {
            "frame_id": 31,
            "timestamp": 1.55,
            "estimated_pose": {"x": 7.0, "y": 8.0, "z": 15.0},
        }
        ws.send_text(json.dumps(valid))
        assert frame_synchronizer._latest_p3.frame_id == 31


def test_navigation_websocket_disconnect_and_reconnect():
    """Verify client disconnect and reconnection lifecycle."""
    # First connection
    with nav_client.websocket_connect("/ws/navigation?source=real") as ws1:
        ws1.send_text(json.dumps({
            "frame_id": 1,
            "timestamp": 0.1,
            "estimated_pose": {"x": 1.0, "y": 1.0, "z": 10.0},
        }))
    # Client 1 disconnected

    # Second connection
    with nav_client.websocket_connect("/ws/navigation?source=real") as ws2:
        ws2.send_text(json.dumps({
            "frame_id": 2,
            "timestamp": 0.2,
            "estimated_pose": {"x": 2.0, "y": 1.0, "z": 10.0},
        }))

    assert frame_synchronizer._latest_p3.frame_id == 2
    assert len(trajectory_repository.get_trajectory().estimated) == 2


def test_simultaneous_p2_camera_and_p3_navigation_isolation():
    """Verify simultaneous P2 camera (/ws/video on main app) and P3 navigation (/ws/navigation on nav_app)."""
    with main_client.websocket_connect("/ws/video?role=viewer") as cam_viewer:
        with main_client.websocket_connect("/ws/video?role=producer") as cam_producer:
            with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
                # 1. P3 sends navigation packet
                nav_ws.send_text(json.dumps({
                    "frame_id": 50,
                    "timestamp": 2.5,
                    "estimated_pose": {"x": 10.0, "y": 20.0, "z": 30.0},
                }))

                # 2. P2 sends binary camera frame
                dummy_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"
                cam_producer.send_bytes(dummy_jpeg)

                received_frame = cam_viewer.receive_bytes()
                assert received_frame.startswith(b"NAVC")
                assert dummy_jpeg in received_frame

                # 3. Verify both systems updated independently
                assert frame_synchronizer._latest_p3.frame_id == 50
                assert camera_service.get_stats()["total_frames"] >= 1
