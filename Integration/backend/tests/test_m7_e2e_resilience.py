"""Milestone 7: End-to-End Real-Time Integration, Synchronization & Resilience Verification Suite.

Validates the complete three-stream architecture:
- Port 8000 /ws/video: Binary JPEG Camera stream (P2 -> P4 -> UI)
- Port 8005 /ws/telemetry: Ground Truth Telemetry (P2 -> P4 Sync)
- Port 8004 /ws/navigation: Navigation Estimates (P3 -> P4 Sync)

Covers all M7 synchronization, health isolation, reconnect recovery, out-of-order,
duplicate, missing frame, and malformed payload tests.
"""

import asyncio
import json
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.camera_service import camera_service
from app.services.frame_sync import frame_synchronizer
from app.repositories.trajectory_repository import trajectory_repository
from app.services.analytics_service import analytics_service
from app.websocket.navigation_server import nav_app
from app.websocket.simulation_server import sim_app


@pytest.fixture(autouse=True)
def reset_system_state():
    """Reset all frame buffers, trajectories, and camera caches before each test."""
    frame_synchronizer.reset()
    trajectory_repository.clear()
    camera_service.reset()
    yield
    frame_synchronizer.reset()
    trajectory_repository.clear()
    camera_service.reset()


# =============================================================================
# 1. THREE-STREAM SIMULTANEOUS OPERATION TEST
# =============================================================================

def test_m7_three_streams_simultaneous():
    """Verify simultaneous operation of Port 8000 (/ws/video), Port 8005 (/ws/telemetry), and Port 8004 (/ws/navigation)."""
    main_client = TestClient(app)
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    # 1. Connect Camera Viewer on 8000
    with main_client.websocket_connect("/ws/video") as cam_viewer:
        # 2. Connect Camera Producer on 8000 with source=real
        with main_client.websocket_connect("/ws/video?role=producer&source=real") as cam_producer:
            # 3. Connect P2 GT Producer on 8005 with source=real
            with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_producer:
                # 4. Connect P3 Navigation Producer on 8004 with source=real
                with nav_client.websocket_connect("/ws/navigation?source=real") as nav_producer:
                    # 5. Connect Frontend Telemetry Viewer on 8000
                    with main_client.websocket_connect("/ws/telemetry") as telem_viewer:
                        # Stream a synchronized cycle for frame_id = 100
                        fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb" + (b"\x00" * 50) + b"\xff\xd9"
                        cam_producer.send_bytes(fake_jpeg)

                        # Receive on viewer
                        received_cam = cam_viewer.receive_bytes()
                        assert len(received_cam) >= len(fake_jpeg)

                        # Stream GT packet on 8005
                        gt_pkt = {
                            "frame_id": 100,
                            "timestamp": 10.0,
                            "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                            "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 90.0},
                            "velocity": {"x": 1.0, "y": 0.0, "z": 0.0},
                        }
                        gt_producer.send_text(json.dumps(gt_pkt))

                        # Stream P3 packet on 8004
                        p3_pkt = {
                            "frame_id": 100,
                            "timestamp": 10.0,
                            "estimated_pose": {"x": 10.2, "y": 20.1, "z": 30.0, "roll": 0.0, "pitch": 0.0, "yaw": 90.5},
                            "velocity": {"x": 1.0, "y": 0.0, "z": 0.0},
                            "tracking_state": "TRACKING_GOOD",
                            "confidence": 0.95,
                            "processing_time_ms": 15.0,
                        }
                        nav_producer.send_text(json.dumps(p3_pkt))

                        # Check frame synchronizer
                        frame = frame_synchronizer.get_frame(100)
                        assert frame is not None
                        assert "p2" in frame.sync_sources
                        assert "p3" in frame.sync_sources

                        # Check trajectory pairs
                        pairs = trajectory_repository.get_synchronized_pairs()
                        assert len(pairs) >= 1
                        assert pairs[-1].frame_id == 100
                        assert pairs[-1].error_3d is not None
                        assert pairs[-1].error_3d < 0.5

                        # Check source health
                        health = frame_synchronizer.get_source_health()
                        assert health["p2"]["state"] == "CONNECTED"
                        assert health["p3"]["state"] == "CONNECTED"
                        assert health["camera"]["state"] == "CONNECTED"


# =============================================================================
# 2. SYNCHRONIZATION HARDENING & EDGE CASE TESTS
# =============================================================================

def test_m7_out_of_order_frame_handling():
    """Verify that an older out-of-order packet does not overwrite newer latest state."""
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
        # 1. Send frame 200 (newer)
        nav_ws.send_text(json.dumps({
            "frame_id": 200,
            "timestamp": 20.0,
            "estimated_pose": {"x": 50.0, "y": 50.0, "z": 10.0},
            "tracking_state": "TRACKING_GOOD",
        }))

        assert frame_synchronizer._latest_p3 is not None
        assert frame_synchronizer._latest_p3.frame_id == 200
        assert frame_synchronizer._latest_p3.estimated_pose.x == 50.0

        # 2. Send frame 190 (delayed / out-of-order)
        nav_ws.send_text(json.dumps({
            "frame_id": 190,
            "timestamp": 19.0,
            "estimated_pose": {"x": 40.0, "y": 40.0, "z": 10.0},
            "tracking_state": "TRACKING_GOOD",
        }))

        # Latest state MUST remain frame 200 (not regressed)
        assert frame_synchronizer._latest_p3.frame_id == 200
        assert frame_synchronizer._latest_p3.estimated_pose.x == 50.0

        # But frame 190 must still be recorded in historical frame buffer
        assert frame_synchronizer.get_frame(190) is not None
        assert frame_synchronizer.get_frame(200) is not None


def test_m7_duplicate_packet_deduplication():
    """Verify that duplicate packets do not double-count in trajectory or analytics."""
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws:
        with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
            # Send frame 50 GT twice
            pkt_gt = {
                "frame_id": 50,
                "timestamp": 5.0,
                "position": {"x": 5.0, "y": 5.0, "z": 5.0},
                "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            }
            gt_ws.send_text(json.dumps(pkt_gt))
            gt_ws.send_text(json.dumps(pkt_gt))

            # Send frame 50 Nav twice
            pkt_nav = {
                "frame_id": 50,
                "timestamp": 5.0,
                "estimated_pose": {"x": 5.1, "y": 5.0, "z": 5.0},
                "tracking_state": "TRACKING_GOOD",
            }
            nav_ws.send_text(json.dumps(pkt_nav))
            nav_ws.send_text(json.dumps(pkt_nav))

            # Trajectory response must not contain duplicates
            traj = trajectory_repository.get_trajectory()
            gt_fids = [p.frame_id for p in traj.ground_truth]
            est_fids = [p.frame_id for p in traj.estimated]
            assert gt_fids.count(50) == 1
            assert est_fids.count(50) == 1

            # Synchronized pairs must have sample_count == 1
            pairs = trajectory_repository.get_synchronized_pairs()
            assert len(pairs) == 1
            assert pairs[0].frame_id == 50


def test_m7_missing_frame_handling():
    """Verify that dropped/missing frames do not fabricate data or crash analytics."""
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws:
        with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
            # Frame 1: Both GT and Nav arrive
            gt_ws.send_text(json.dumps({"frame_id": 1, "timestamp": 0.1, "position": {"x": 1.0, "y": 0.0, "z": 0.0}, "orientation": {"roll": 0, "pitch": 0, "yaw": 0}}))
            nav_ws.send_text(json.dumps({"frame_id": 1, "timestamp": 0.1, "estimated_pose": {"x": 1.0, "y": 0.0, "z": 0.0}}))

            # Frame 2: Only GT arrives (Nav dropped frame 2)
            gt_ws.send_text(json.dumps({"frame_id": 2, "timestamp": 0.2, "position": {"x": 2.0, "y": 0.0, "z": 0.0}, "orientation": {"roll": 0, "pitch": 0, "yaw": 0}}))

            # Frame 3: Both GT and Nav arrive
            gt_ws.send_text(json.dumps({"frame_id": 3, "timestamp": 0.3, "position": {"x": 3.0, "y": 0.0, "z": 0.0}, "orientation": {"roll": 0, "pitch": 0, "yaw": 0}}))
            nav_ws.send_text(json.dumps({"frame_id": 3, "timestamp": 0.3, "estimated_pose": {"x": 3.1, "y": 0.0, "z": 0.0}}))

            # Matched pairs should only include frames 1 and 3 (no fabricated frame 2)
            pairs = trajectory_repository.get_synchronized_pairs()
            matched_fids = [p.frame_id for p in pairs]
            assert 1 in matched_fids
            assert 3 in matched_fids
            assert 2 not in matched_fids

            # Analytics compute cleanly
            metrics = analytics_service.compute_metrics()
            assert metrics.sample_count == 2
            assert metrics.ate.mean is not None


# =============================================================================
# 3. FAILURE ISOLATION AND RECOVERY TESTS (Section 25)
# =============================================================================

def test_m7_failure_a_p3_disconnect():
    """Failure A: P3 disconnects; P2 camera and GT continue operating unaffected."""
    main_client = TestClient(app)
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    # 1. Connect all three
    with main_client.websocket_connect("/ws/video?role=producer&source=real") as cam_ws:
        with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws:
            with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
                # Send data
                cam_ws.send_bytes(b"\xff\xd8\xff\xd9")
                gt_ws.send_text(json.dumps({"frame_id": 1, "position": {"x": 0, "y": 0, "z": 0}}))
                nav_ws.send_text(json.dumps({"frame_id": 1, "estimated_pose": {"x": 0, "y": 0, "z": 0}}))

            # P3 nav_ws has now disconnected
            # P2 camera and GT send more data
            cam_ws.send_bytes(b"\xff\xd8\xff\xd9")
            gt_ws.send_text(json.dumps({"frame_id": 2, "position": {"x": 1, "y": 1, "z": 1}}))

            # Check health
            health = frame_synchronizer.get_source_health()
            assert health["camera"]["packet_count"] >= 2
            assert health["p2"]["packet_count"] >= 2
            assert health["camera"]["state"] == "CONNECTED"
            assert health["p2"]["state"] == "CONNECTED"


def test_m7_failure_b_camera_disconnect():
    """Failure B: Camera disconnects; GT and P3 continue operating unaffected."""
    main_client = TestClient(app)
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws:
        with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
            with main_client.websocket_connect("/ws/video?role=producer&source=real") as cam_ws:
                cam_ws.send_bytes(b"\xff\xd8\xff\xd9")
                gt_ws.send_text(json.dumps({"frame_id": 1, "position": {"x": 0, "y": 0, "z": 0}}))
                nav_ws.send_text(json.dumps({"frame_id": 1, "estimated_pose": {"x": 0, "y": 0, "z": 0}}))

            # Camera disconnected
            gt_ws.send_text(json.dumps({"frame_id": 2, "position": {"x": 1, "y": 1, "z": 1}}))
            nav_ws.send_text(json.dumps({"frame_id": 2, "estimated_pose": {"x": 1, "y": 1, "z": 1}}))

            health = frame_synchronizer.get_source_health()
            assert health["p2"]["packet_count"] == 2
            assert health["p3"]["packet_count"] == 2
            assert health["p2"]["state"] == "CONNECTED"
            assert health["p3"]["state"] == "CONNECTED"


def test_m7_failure_c_gt_disconnect():
    """Failure C: P2 GT disconnects; Camera and P3 continue operating unaffected."""
    main_client = TestClient(app)
    sim_client = TestClient(sim_app)
    nav_client = TestClient(nav_app)

    with main_client.websocket_connect("/ws/video?role=producer&source=real") as cam_ws:
        with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
            with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws:
                gt_ws.send_text(json.dumps({"frame_id": 1, "position": {"x": 0, "y": 0, "z": 0}}))
                cam_ws.send_bytes(b"\xff\xd8\xff\xd9")
                nav_ws.send_text(json.dumps({"frame_id": 1, "estimated_pose": {"x": 0, "y": 0, "z": 0}}))

            # GT disconnected
            cam_ws.send_bytes(b"\xff\xd8\xff\xd9")
            nav_ws.send_text(json.dumps({"frame_id": 2, "estimated_pose": {"x": 1, "y": 1, "z": 1}}))

            health = frame_synchronizer.get_source_health()
            assert health["camera"]["packet_count"] == 2
            assert health["p3"]["packet_count"] == 2
            assert health["camera"]["state"] == "CONNECTED"
            assert health["p3"]["state"] == "CONNECTED"


def test_m7_failure_d_reconnect():
    """Failure D: A disconnected source reconnects and immediately transitions to CONNECTED without backend restart."""
    sim_client = TestClient(sim_app)

    # First session
    with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws:
        gt_ws.send_text(json.dumps({"frame_id": 1, "position": {"x": 0, "y": 0, "z": 0}}))

    # Simulate stale delay
    frame_synchronizer._last_p2_time = time.time() - (settings.STALE_TIMEOUT_SEC + 1.0)
    health_stale = frame_synchronizer.get_source_health()
    assert health_stale["p2"]["state"] == "STALE"

    # Reconnect session
    with sim_client.websocket_connect("/ws/telemetry?source=real") as gt_ws2:
        gt_ws2.send_text(json.dumps({"frame_id": 2, "position": {"x": 1, "y": 1, "z": 1}}))

    # Must immediately recover to CONNECTED (REAL / ONLINE)
    health_recovered = frame_synchronizer.get_source_health()
    assert health_recovered["p2"]["state"] == "CONNECTED"
    assert health_recovered["p2"]["is_real"] is True


def test_m7_failure_h_malformed_json():
    """Failure H: Malformed JSON is rejected with error, socket remains alive, subsequent packets work."""
    nav_client = TestClient(nav_app)

    with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
        # 1. Send completely invalid JSON text
        nav_ws.send_text("{ invalid_json: this is bad content }")

        # Receiver should respond with error JSON but NOT terminate
        err_msg = nav_ws.receive_json()
        assert err_msg.get("status") == "error"
        assert err_msg.get("code") == "INVALID_JSON"

        # 2. Send schema-invalid JSON
        nav_ws.send_text(json.dumps({"invalid_field": "no frame_id or pose"}))
        err_msg2 = nav_ws.receive_json()
        assert err_msg2.get("status") == "error"
        assert err_msg2.get("code") == "VALIDATION_FAILED"

        # 3. Send valid packet on same socket
        valid_pkt = {
            "frame_id": 300,
            "timestamp": 30.0,
            "estimated_pose": {"x": 12.0, "y": 14.0, "z": 16.0},
            "tracking_state": "TRACKING_GOOD",
        }
        nav_ws.send_text(json.dumps(valid_pkt))

        # Check ingestion succeeded
        assert frame_synchronizer._latest_p3 is not None
        assert frame_synchronizer._latest_p3.frame_id == 300


# =============================================================================
# 4. REQUIRED VERIFICATION ENDPOINTS TEST (Section 23)
# =============================================================================

def test_m7_verification_endpoints():
    """Verify /api/v1/integration/health and /api/v1/navigation/state/latest endpoints."""
    main_client = TestClient(app)
    nav_client = TestClient(nav_app)

    # Push a valid navigation frame on 8004
    with nav_client.websocket_connect("/ws/navigation?source=real") as nav_ws:
        nav_ws.send_text(json.dumps({
            "frame_id": 777,
            "timestamp": 77.7,
            "estimated_pose": {"x": 1.23, "y": 4.56, "z": 7.89, "roll": 0.1, "pitch": 0.2, "yaw": 30.0},
            "velocity": {"x": 0.5, "y": 0.0, "z": 0.1},
            "tracking_state": "TRACKING_GOOD",
            "confidence": 0.98,
            "processing_time_ms": 12.5,
        }))

    # 1. Test GET /api/v1/integration/health
    resp_health = main_client.get("/api/v1/integration/health")
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    assert "p3" in health_data
    assert health_data["p3"]["state"] == "CONNECTED"
    assert health_data["p3"]["last_frame_id"] == 777

    # 2. Test GET /api/v1/navigation/state/latest
    resp_nav = main_client.get("/api/v1/navigation/state/latest")
    assert resp_nav.status_code == 200
    nav_data = resp_nav.json()
    assert nav_data["frame_id"] == 777
    assert nav_data["estimated_pose"]["x"] == 1.23
    assert nav_data["confidence"] == 0.98
    assert nav_data["tracking_state"] == "TRACKING_GOOD"
