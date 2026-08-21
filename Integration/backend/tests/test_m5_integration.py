"""Milestone 5 Integration and Contract Verification Test Suite.

Validates:
- Real P1 contract format ingestion, aliasing, and error resilience
- Real P2 contract format ingestion with nested ground_truth dict
- Real P3 navigation state ingestion, velocity array handling, and telemetry update
- Multi-source frame synchronization (P1, P2, P3) and partial data tolerance
- Out-of-order and duplicate frame handling
- Trajectory synchronization and Euclidean localization error calculation
- Real NavigationEngine processing and output schema compatibility
"""

import math
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket
from app.services.frame_sync import frame_synchronizer
from app.repositories.trajectory_repository import trajectory_repository
from app.services.analytics_service import analytics_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset synchronizer and trajectory repository before each test."""
    frame_synchronizer.reset()
    trajectory_repository.clear()
    yield
    frame_synchronizer.reset()
    trajectory_repository.clear()


# =========================================================================
# 1. P1 REAL DATA CONTRACT INGESTION TESTS
# =========================================================================

def test_p1_contract_representative_packet():
    """Test representative P1 contract JSON packet defined in specification."""
    payload = {
        "frame_id": 125,
        "terrain": {
            "class": "forest",
            "confidence": 0.97,
        },
        "landmarks": [
            {
                "class": "tree",
                "confidence": 0.94,
                "bbox": [220, 130, 310, 420],
            },
            {
                "class": "road",
                "confidence": 0.91,
                "bbox": [0, 500, 1280, 720],
            },
        ],
        "segmentation_mask": "masks/frame_0125.png",
        "place_recognition": {
            "location_id": 14,
            "confidence": 0.93,
        },
    }

    res = client.post("/api/v1/perception/result", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["frame_id"] == 125
    assert "p1" in data["sync_sources"]

    # Verify latest perception endpoint properly mapped all fields
    latest_res = client.get("/api/v1/perception/latest")
    assert latest_res.status_code == 200
    latest = latest_res.json()
    assert latest["frame_id"] == 125
    assert latest["terrain"]["terrain_type"] == "forest"
    assert latest["terrain"]["confidence"] == 0.97
    assert len(latest["landmarks"]) == 2
    assert latest["landmarks"][0]["label"] == "tree"
    assert latest["landmarks"][1]["label"] == "road"
    assert latest["segmentation"]["mask_path"] == "masks/frame_0125.png"
    assert latest["place_recognition"]["match_found"] is True
    assert latest["place_recognition"]["location_id"] == "14"
    assert latest["place_recognition"]["similarity_score"] == 0.93


def test_p1_malformed_packet_rejected_cleanly():
    """Test malformed P1 packet without frame_id returns 422 without crashing."""
    payload = {
        "terrain": {"class": "forest"},
        # missing frame_id
    }
    res = client.post("/api/v1/perception/result", json=payload)
    assert res.status_code == 422


# =========================================================================
# 2. P2 REAL DATA CONTRACT INGESTION TESTS
# =========================================================================

def test_p2_contract_representative_packet():
    """Test representative P2 ground truth contract JSON packet."""
    payload = {
        "frame_id": 125,
        "timestamp": 4.166,
        "ground_truth": {
            "x": 10.50,
            "y": 5.90,
            "z": 20.00,
            "roll": 0.2,
            "pitch": 1.0,
            "yaw": 90.0,
        },
        "camera": {
            "image_path": "frames/frame_0125.png",
        },
    }

    res = client.post("/api/v1/simulation/ground-truth", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["frame_id"] == 125
    assert "p2" in data["sync_sources"]

    # Verify latest ground truth endpoint
    latest_res = client.get("/api/v1/simulation/ground-truth/latest")
    assert latest_res.status_code == 200
    latest = latest_res.json()
    assert latest["frame_id"] == 125
    assert latest["position"]["x"] == 10.50
    assert latest["position"]["y"] == 5.90
    assert latest["position"]["z"] == 20.00
    assert latest["orientation"]["roll"] == 0.2
    assert latest["orientation"]["pitch"] == 1.0
    assert latest["orientation"]["yaw"] == 90.0
    assert latest["camera"]["image_path"] == "frames/frame_0125.png"


def test_p2_malformed_packet_rejected():
    """Test malformed P2 ground truth packet returns 422."""
    payload = {
        "frame_id": 125,
        "ground_truth": "invalid_string_not_dict",
    }
    res = client.post("/api/v1/simulation/ground-truth", json=payload)
    assert res.status_code == 422


# =========================================================================
# 3. P3 REAL DATA CONTRACT INGESTION & TELEMETRY SOURCE TESTS
# =========================================================================

def test_p3_contract_representative_packet():
    """Test representative P3 navigation contract JSON packet."""
    payload = {
        "frame_id": 125,
        "timestamp": 4.166,
        "estimated_pose": {
            "x": 10.42,
            "y": 5.81,
            "z": 20.13,
            "roll": 0.3,
            "pitch": 1.1,
            "yaw": 89.7,
        },
        "velocity": {
            "x": 3.2,
            "y": 0.0,
            "z": 0.1,
        },
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.96,
        "processing_time_ms": 18,
    }

    res = client.post("/api/v1/navigation/state", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["frame_id"] == 125
    assert "p3" in data["sync_sources"]

    # Verify latest navigation state endpoint
    latest_res = client.get("/api/v1/navigation/state/latest")
    assert latest_res.status_code == 200
    latest = latest_res.json()
    assert latest["frame_id"] == 125
    assert latest["estimated_pose"]["x"] == 10.42
    assert latest["estimated_pose"]["y"] == 5.81
    assert latest["estimated_pose"]["z"] == 20.13
    assert latest["confidence"] == 0.96
    assert latest["tracking_state"] == "TRACKING_GOOD"


def test_p3_velocity_array_and_telemetry_source():
    """Verify telemetry endpoint reflects P3 estimated pose, not P2 ground truth."""
    # Ingest P2 GT at (100.0, 50.0, 30.0)
    p2_payload = {
        "frame_id": 50,
        "timestamp": 1.5,
        "ground_truth": {"x": 100.0, "y": 50.0, "z": 30.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    }
    client.post("/api/v1/simulation/ground-truth", json=p2_payload)

    # Ingest P3 Navigation estimate at (10.42, 5.81, 20.13) with velocity as list
    p3_payload = {
        "frame_id": 50,
        "timestamp": 1.5,
        "estimated_pose": {"x": 10.42, "y": 5.81, "z": 20.13, "roll": 0.3, "pitch": 1.1, "yaw": 89.7},
        "velocity": [3.2, 0.0, 0.1],
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.95,
    }
    res = client.post("/api/v1/navigation/state", json=p3_payload)
    assert res.status_code == 200

    # Verify /api/v1/telemetry/current uses P3 estimated pose
    tel_res = client.get("/api/v1/telemetry/current")
    assert tel_res.status_code == 200
    tel = tel_res.json()
    assert tel["x"] == 10.42
    assert tel["y"] == 5.81
    assert tel["z"] == 20.13
    assert tel["yaw"] == 89.7
    assert tel["confidence"] == 0.95


# =========================================================================
# 4. SYNCHRONIZATION, PARTIAL DATA, AND OUT-OF-ORDER TESTS
# =========================================================================

def test_full_three_source_synchronization():
    """Verify frame synchronizer successfully aligns P1, P2, and P3 on frame_id."""
    frame_id = 77
    ts = 2.56

    client.post("/api/v1/simulation/ground-truth", json={
        "frame_id": frame_id,
        "timestamp": ts,
        "ground_truth": {"x": 15.0, "y": 25.0, "z": 10.0, "roll": 0, "pitch": 0, "yaw": 45},
    })
    client.post("/api/v1/navigation/state", json={
        "frame_id": frame_id,
        "timestamp": ts,
        "estimated_pose": {"x": 15.1, "y": 24.9, "z": 10.05, "roll": 0, "pitch": 0, "yaw": 44.8},
    })
    client.post("/api/v1/perception/result", json={
        "frame_id": frame_id,
        "timestamp": ts,
        "terrain": {"class": "forest", "confidence": 0.95},
    })

    # Retrieve integrated frame
    frame_res = client.get(f"/api/v1/integration/frames/{frame_id}")
    assert frame_res.status_code == 200
    frame_data = frame_res.json()
    assert frame_data["frame_id"] == frame_id
    assert set(frame_data["sync_sources"]) == {"p1", "p2", "p3"}
    assert frame_data["ground_truth"] is not None
    assert frame_data["navigation"] is not None
    assert frame_data["perception"] is not None


def test_partial_data_tolerance_p2_p3_without_p1():
    """System operates smoothly when P1 is delayed/absent."""
    frame_id = 88
    client.post("/api/v1/simulation/ground-truth", json={
        "frame_id": frame_id,
        "timestamp": 3.0,
        "ground_truth": {"x": 20.0, "y": 10.0, "z": 12.0, "roll": 0, "pitch": 0, "yaw": 0},
    })
    client.post("/api/v1/navigation/state", json={
        "frame_id": frame_id,
        "timestamp": 3.0,
        "estimated_pose": {"x": 20.05, "y": 9.95, "z": 12.0, "roll": 0, "pitch": 0, "yaw": 0},
    })

    frame_res = client.get(f"/api/v1/integration/frames/{frame_id}")
    assert frame_res.status_code == 200
    frame_data = frame_res.json()
    assert "p2" in frame_data["sync_sources"]
    assert "p3" in frame_data["sync_sources"]
    assert "p1" not in frame_data["sync_sources"]
    assert frame_data["perception"] is None


def test_out_of_order_and_duplicate_frame_handling():
    """Verify out-of-order packets and duplicate updates are handled gracefully."""
    # Ingest frame 200 then frame 190
    client.post("/api/v1/navigation/state", json={
        "frame_id": 200,
        "timestamp": 6.66,
        "estimated_pose": {"x": 50.0, "y": 30.0, "z": 15.0, "roll": 0, "pitch": 0, "yaw": 0},
    })
    client.post("/api/v1/navigation/state", json={
        "frame_id": 190,
        "timestamp": 6.33,
        "estimated_pose": {"x": 45.0, "y": 28.0, "z": 15.0, "roll": 0, "pitch": 0, "yaw": 0},
    })

    # Recent frames should be sorted in ascending order of frame_id
    rec_res = client.get("/api/v1/integration/frames?limit=10")
    assert rec_res.status_code == 200
    frames = rec_res.json()
    assert len(frames) >= 2
    frame_ids = [f["frame_id"] for f in frames]
    assert frame_ids == sorted(frame_ids)

    # Duplicate ingestion of frame 200 with updated confidence
    dup_res = client.post("/api/v1/navigation/state", json={
        "frame_id": 200,
        "timestamp": 6.66,
        "estimated_pose": {"x": 50.0, "y": 30.0, "z": 15.0, "roll": 0, "pitch": 0, "yaw": 0},
        "confidence": 0.99,
    })
    assert dup_res.status_code == 200


# =========================================================================
# 5. ANALYTICS & LOCALIZATION ERROR COMPUTATION TESTS
# =========================================================================

def test_synchronized_localization_error_calculation():
    """Verify Euclidean 3D localization error calculation against contract values."""
    # Ingest corresponding frame 125 for P2 and P3
    client.post("/api/v1/simulation/ground-truth", json={
        "frame_id": 125,
        "timestamp": 4.166,
        "ground_truth": {"x": 10.50, "y": 5.90, "z": 20.00, "roll": 0.2, "pitch": 1.0, "yaw": 90.0},
    })
    client.post("/api/v1/navigation/state", json={
        "frame_id": 125,
        "timestamp": 4.166,
        "estimated_pose": {"x": 10.42, "y": 5.81, "z": 20.13, "roll": 0.3, "pitch": 1.1, "yaw": 89.7},
    })

    # Expected Euclidean error:
    # dx = 10.42 - 10.50 = -0.08
    # dy = 5.81 - 5.90 = -0.09
    # dz = 20.13 - 20.00 = 0.13
    # err = sqrt((-0.08)^2 + (-0.09)^2 + 0.13^2) = sqrt(0.0064 + 0.0081 + 0.0169) = sqrt(0.0314) ≈ 0.1772
    expected_err = math.sqrt((-0.08)**2 + (-0.09)**2 + 0.13**2)

    res = client.get("/api/v1/analytics/current")
    assert res.status_code == 200
    data = res.json()
    assert data["sample_count"] >= 1
    cur_err = data["localization_error"]["current"]
    assert pytest.approx(cur_err, abs=0.005) == expected_err
    assert data["localization_error"]["dx"] == -0.08
    assert data["localization_error"]["dy"] == -0.09
    assert data["localization_error"]["dz"] == 0.13


# =========================================================================
# 6. REAL NAVIGATION ENGINE (P3) SCHEMA COMPATIBILITY TEST
# =========================================================================

def test_real_p3_navigation_engine_pipeline():
    """Verify that real NavigationEngine from navigation module outputs valid P4 schema."""
    import sys
    import os
    # Add navigation directory to path if not present
    nav_dir = r"C:\SIH\Naevis\navigation"
    if nav_dir not in sys.path:
        sys.path.insert(0, nav_dir)

    try:
        import numpy as np
        from navigation.engine import NavigationEngine
    except ImportError as e:
        pytest.skip(f"navigation engine import skipped: {e}")

    engine = NavigationEngine(waypoints=[
        {"id": 1, "name": "Takeoff", "x": 0.0, "y": 0.0, "z": 5.0, "speed": 2.0},
        {"id": 2, "name": "Target_A", "x": 10.0, "y": 5.0, "z": 6.0, "speed": 3.5}
    ])

    sensor_packet = {
        "frame_id": 1,
        "timestamp": 0.033,
        "camera": {"frame": np.zeros((240, 320, 3), dtype=np.uint8)},
        "imu": {"acceleration": [0.0, 0.0, 9.81], "gyroscope": [0.0, 0.0, 0.0]}
    }

    # Run real P3 engine
    output = engine.process_packet(sensor_packet)
    assert "frame_id" in output
    assert "estimated_pose" in output
    assert "velocity" in output
    assert "tracking_state" in output
    assert "confidence" in output

    # Ingest output directly into P4 backend endpoint
    res = client.post("/api/v1/navigation/state", json=output)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
