"""Unit tests for Milestone 6 Adapter & Normalization Layer (P1, P2, P3)."""

import math
import pytest
from app.integrations.p1.adapter import normalize_p1_payload
from app.integrations.p2.adapter import normalize_p2_ground_truth
from app.integrations.p3.adapter import normalize_p3_navigation
from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket


# =============================================================================
# P1 Perception Adapter Tests
# =============================================================================

def test_p1_adapter_valid_payload():
    raw = {
        "frame_id": 10,
        "timestamp": 1.25,
        "terrain": {
            "terrain_type": "urban",
            "confidence": 0.95,
            "roughness": 0.1,
            "features": ["road", "building"],
        },
        "landmarks": [
            {
                "landmark_id": "LM_1",
                "label": "tower",
                "confidence": 0.9,
                "bbox": [10.0, 20.0, 50.0, 60.0],
                "estimated_relative_pos": {"x": 5.0, "y": 2.0, "z": -1.0},
            }
        ],
    }
    result = normalize_p1_payload(raw)
    assert isinstance(result, P1VisionResult)
    assert result.frame_id == 10
    assert result.timestamp == 1.25
    assert result.terrain.terrain_type == "urban"
    assert len(result.landmarks) == 1
    assert result.landmarks[0].label == "tower"


def test_p1_adapter_alias_handling():
    raw = {
        "frame_id": 15,
        "terrain": {"class": "forest", "confidence": 0.88},
        "landmarks": [{"class": "tree_cluster", "confidence": 0.92}],
    }
    result = normalize_p1_payload(raw)
    assert result.terrain.terrain_type == "forest"
    assert result.landmarks[0].label == "tree_cluster"


def test_p1_adapter_rejects_nan_and_inf():
    # NaN in landmark relative pos
    raw = {
        "frame_id": 1,
        "landmarks": [
            {
                "label": "test",
                "estimated_relative_pos": {"x": float("nan"), "y": 0.0, "z": 0.0},
            }
        ],
    }
    with pytest.raises(ValueError, match="non-finite"):
        normalize_p1_payload(raw)

    # Inf in timestamp
    raw_inf = {"frame_id": 1, "timestamp": float("inf")}
    with pytest.raises(ValueError, match="non-finite"):
        normalize_p1_payload(raw_inf)


def test_p1_adapter_rejects_out_of_bounds_confidence():
    raw_high = {"frame_id": 1, "terrain": {"confidence": 1.5}}
    with pytest.raises(ValueError, match="out of bounds"):
        normalize_p1_payload(raw_high)

    raw_neg = {"frame_id": 1, "terrain": {"confidence": -0.1}}
    with pytest.raises(ValueError, match="out of bounds"):
        normalize_p1_payload(raw_neg)


def test_p1_adapter_rejects_invalid_bbox():
    raw_bbox = {
        "frame_id": 1,
        "landmarks": [{"label": "test", "bbox": [10.0, 20.0, 30.0]}],  # only 3 coords
    }
    with pytest.raises(ValueError, match="4 coordinates"):
        normalize_p1_payload(raw_bbox)


# =============================================================================
# P2 Simulation Ground Truth Adapter Tests
# =============================================================================

def test_p2_adapter_nested_format():
    raw = {
        "frame_id": 100,
        "timestamp": 5.0,
        "position": {"x": 12.5, "y": -4.2, "z": 20.0},
        "orientation": {"roll": 1.5, "pitch": -2.0, "yaw": 45.0},
        "lidar": {"front": 15.0, "bottom": 20.0},
    }
    result = normalize_p2_ground_truth(raw)
    assert isinstance(result, SimulationGroundTruthPacket)
    assert result.frame_id == 100
    assert result.position.x == 12.5
    assert result.orientation.yaw == 45.0
    assert result.lidar.front == 15.0


def test_p2_adapter_flat_format():
    raw = {
        "frame_id": 101,
        "timestamp": 5.1,
        "x": 10.0,
        "y": 20.0,
        "z": 30.0,
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 90.0,
    }
    result = normalize_p2_ground_truth(raw)
    assert result.position.x == 10.0
    assert result.position.y == 20.0
    assert result.position.z == 30.0
    assert result.orientation.yaw == 90.0


def test_p2_adapter_rejects_nan_coordinates():
    raw = {
        "frame_id": 1,
        "position": {"x": float("nan"), "y": 0.0, "z": 10.0},
    }
    with pytest.raises(ValueError, match="non-finite"):
        normalize_p2_ground_truth(raw)


def test_p2_adapter_rejects_missing_position():
    raw = {"frame_id": 1, "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}}
    with pytest.raises(ValueError, match="Missing required position"):
        normalize_p2_ground_truth(raw)


# =============================================================================
# P3 Navigation State Adapter Tests
# =============================================================================

def test_p3_adapter_nested_format():
    raw = {
        "frame_id": 200,
        "timestamp": 8.5,
        "estimated_pose": {
            "x": 5.2,
            "y": 14.8,
            "z": 18.0,
            "roll": 0.2,
            "pitch": -0.1,
            "yaw": 88.5,
        },
        "velocity": {"x": 2.5, "y": 0.1, "z": -0.2},
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.97,
    }
    result = normalize_p3_navigation(raw)
    assert isinstance(result, NavigationStatePacket)
    assert result.frame_id == 200
    assert result.estimated_pose.x == 5.2
    assert result.velocity.x == 2.5
    assert result.tracking_state == "TRACKING_GOOD"
    assert result.confidence == 0.97


def test_p3_adapter_flat_and_list_velocity():
    raw = {
        "frame_id": 201,
        "timestamp": 8.6,
        "x": 6.0,
        "y": 15.0,
        "z": 18.0,
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 90.0,
        "velocity": [3.0, 0.0, 0.0],
        "flight_command": {"desired_velocity_mps": 3.0},
    }
    result = normalize_p3_navigation(raw)
    assert result.estimated_pose.x == 6.0
    assert result.velocity.x == 3.0
    assert result.flight_command["desired_velocity_mps"] == 3.0


def test_p3_adapter_rejects_nan_pose():
    raw = {
        "frame_id": 1,
        "estimated_pose": {"x": 0.0, "y": float("nan"), "z": 10.0},
    }
    with pytest.raises(ValueError, match="non-finite"):
        normalize_p3_navigation(raw)
