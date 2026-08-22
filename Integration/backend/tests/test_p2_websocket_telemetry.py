"""Unit and Integration tests for Dedicated P2 Simulation Ground Truth WebSocket Server (Port 8005)."""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app as main_app
from app.websocket.navigation_server import nav_app
from app.websocket.simulation_server import sim_app
from app.services.frame_sync import frame_synchronizer
from app.services.camera_service import camera_service
from app.repositories.trajectory_repository import trajectory_repository

main_client = TestClient(main_app)
nav_client = TestClient(nav_app)
sim_client = TestClient(sim_app)


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


def test_simulation_server_health_and_root():
    """Verify HTTP endpoints on dedicated port 8005 simulation server."""
    health_resp = sim_client.get("/health")
    assert health_resp.status_code == 200
    data = health_resp.json()
    assert data["status"] == "online"
    assert data["port"] == 8005

    root_resp = sim_client.get("/")
    assert root_resp.status_code == 200
    assert root_resp.json()["service"] == "P2 Simulation Ground Truth Receiver"


def test_p2_telemetry_valid_real_packet_port_8005():
    """Verify valid P2 ground truth packet ingestion over port 8005 /ws/telemetry preserves frame_id and timestamp."""
    valid_payload = {
        "frame_id": 125,
        "timestamp": 4.166,
        "ground_truth": {
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
        "lidar": {
            "front": 18.5,
            "bottom": 12.0,
        },
    }

    with sim_client.websocket_connect("/ws/telemetry?source=real") as ws:
        ws.send_text(json.dumps(valid_payload))

        # Verify frame synchronizer updated
        assert frame_synchronizer._latest_p2 is not None
        assert frame_synchronizer._latest_p2.frame_id == 125
        assert frame_synchronizer._latest_p2.timestamp == 4.166
        assert frame_synchronizer._latest_p2.position.x == 10.42
        assert frame_synchronizer._latest_p2.orientation.yaw == 89.7

        # Verify source health indicates CONNECTED and is_real=True
        health = frame_synchronizer.get_source_health()
        assert health["p2"]["state"] == "CONNECTED"
        assert health["p2"]["is_real"] is True
        assert health["p2"]["last_frame_id"] == 125

        # Verify trajectory repository recorded ground truth point separately
        traj = trajectory_repository.get_trajectory(limit=10)
        assert len(traj.ground_truth) == 1
        assert traj.ground_truth[0].frame_id == 125
        assert traj.ground_truth[0].x == 10.42


def test_p2_telemetry_mock_provenance_port_8005():
    """Verify ?source=mock records as MOCK in source health."""
    payload = {
        "frame_id": 10,
        "timestamp": 0.5,
        "position": {"x": 1.0, "y": 2.0, "z": 10.0},
        "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    }

    with sim_client.websocket_connect("/ws/telemetry?source=mock") as ws:
        ws.send_text(json.dumps(payload))

        health = frame_synchronizer.get_source_health()
        assert health["p2"]["state"] == "MOCK"
        assert health["p2"]["is_real"] is False


def test_p2_telemetry_invalid_json_resilience_port_8005():
    """Verify invalid JSON payload does not crash server or terminate connection."""
    with sim_client.websocket_connect("/ws/telemetry?source=real") as ws:
        # 1. Send invalid JSON
        ws.send_text("not_a_valid_json{{")
        err = ws.receive_json()
        assert err["status"] == "error"
        assert err["code"] == "INVALID_JSON"

        # 2. Subsequent valid packet
        valid = {
            "frame_id": 15,
            "timestamp": 0.75,
            "position": {"x": 5.0, "y": 5.0, "z": 15.0},
        }
        ws.send_text(json.dumps(valid))
        assert frame_synchronizer._latest_p2.frame_id == 15


def test_p2_telemetry_schema_validation_failure_resilience_port_8005():
    """Verify missing position fields are rejected without corrupting state."""
    with sim_client.websocket_connect("/ws/telemetry?source=real") as ws:
        # 1. Missing position
        invalid_schema = {"frame_id": 20, "timestamp": 1.0}
        ws.send_text(json.dumps(invalid_schema))
        err = ws.receive_json()
        assert err["status"] == "error"
        assert err["code"] == "VALIDATION_FAILED"

        # 2. Subsequent valid packet
        valid = {
            "frame_id": 21,
            "timestamp": 1.05,
            "position": {"x": 7.0, "y": 8.0, "z": 20.0},
        }
        ws.send_text(json.dumps(valid))
        assert frame_synchronizer._latest_p2.frame_id == 21


def test_p2_telemetry_disconnect_and_reconnect_port_8005():
    """Verify client disconnect and reconnect lifecycle."""
    with sim_client.websocket_connect("/ws/telemetry?source=real") as ws1:
        ws1.send_text(json.dumps({
            "frame_id": 1,
            "timestamp": 0.1,
            "position": {"x": 1.0, "y": 1.0, "z": 10.0},
        }))

    # Reconnect with new client session
    with sim_client.websocket_connect("/ws/telemetry?source=real") as ws2:
        ws2.send_text(json.dumps({
            "frame_id": 2,
            "timestamp": 0.2,
            "position": {"x": 2.0, "y": 1.0, "z": 10.0},
        }))

    assert frame_synchronizer._latest_p2.frame_id == 2
    assert len(trajectory_repository.get_trajectory().ground_truth) == 2


def test_simultaneous_isolated_camera_telemetry_navigation():
    """Verify simultaneous operation across all 3 dedicated ports: Port 8000 (/ws/video), Port 8005 (/ws/telemetry), Port 8004 (/ws/navigation)."""
    # 1. P2 Camera Producer on port 8000 (/ws/video)
    with main_client.websocket_connect("/ws/video?role=producer") as cam_producer:
        # 2. P2 Telemetry Producer on dedicated port 8005 (/ws/telemetry)
        with sim_client.websocket_connect("/ws/telemetry?source=real") as p2_ws:
            # 3. P3 Navigation Producer on dedicated port 8004 (/ws/navigation)
            with nav_client.websocket_connect("/ws/navigation?source=real") as p3_ws:
                # 4. Frontend Viewer on port 8000 (/ws/telemetry)
                with main_client.websocket_connect("/ws/telemetry?role=viewer") as viewer_ws:
                    # Ingest initial snapshots
                    _ = viewer_ws.receive_json()

                    # Send P2 camera frame
                    dummy_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"
                    cam_producer.send_bytes(dummy_jpeg)

                    # Send P2 ground truth telemetry on port 8005
                    p2_ws.send_text(json.dumps({
                        "frame_id": 100,
                        "timestamp": 5.0,
                        "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                        "orientation": {"roll": 1.0, "pitch": 0.0, "yaw": 90.0},
                    }))

                    # Send P3 estimated navigation on port 8004
                    p3_ws.send_text(json.dumps({
                        "frame_id": 100,
                        "timestamp": 5.0,
                        "estimated_pose": {"x": 10.2, "y": 19.8, "z": 29.9, "roll": 1.0, "pitch": 0.0, "yaw": 89.5},
                    }))

                    # Verify synchronized states
                    assert frame_synchronizer._latest_p2.frame_id == 100
                    assert frame_synchronizer._latest_p3.frame_id == 100
                    assert camera_service.get_stats()["total_frames"] >= 1

                    # Verify trajectory separation
                    traj = trajectory_repository.get_trajectory()
                    assert len(traj.ground_truth) >= 1
                    assert len(traj.estimated) >= 1
                    assert traj.ground_truth[-1].x == 10.0
                    assert traj.estimated[-1].x == 10.2
