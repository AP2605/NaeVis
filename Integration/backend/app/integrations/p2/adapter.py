"""P2 Simulation Ground Truth and Camera Adapter Layer.

Normalizes incoming simulation ground truth and camera reference payloads from P2 (Blender)
into validated P4 internal models, rejecting corrupted or non-physical data (NaN, Inf).
"""

import math
from typing import Any
from pydantic import ValidationError

from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.common import Position3D, Orientation3D, LidarData, CameraReference


def _check_finite(val: float | None, name: str) -> float | None:
    """Check that a float value is finite and not NaN or Infinity."""
    if val is not None:
        try:
            f_val = float(val)
        except (TypeError, ValueError) as err:
            raise ValueError(f"Field '{name}' must be a valid number: {err}") from err
        if not math.isfinite(f_val):
            raise ValueError(f"Field '{name}' has non-finite value: {f_val}")
    return val


def normalize_p2_ground_truth(raw_data: Any, is_real: bool = False) -> SimulationGroundTruthPacket:
    """Normalize and validate incoming P2 ground truth packet.

    Args:
        raw_data: Raw dictionary or SimulationGroundTruthPacket instance.
        is_real: Flag indicating whether packet is from real Blender simulation.

    Returns:
        Validated SimulationGroundTruthPacket model.

    Raises:
        ValueError: If packet structure is malformed, missing required fields, or contains NaN/Inf.
    """
    if isinstance(raw_data, SimulationGroundTruthPacket):
        packet_dict = raw_data.model_dump()
    elif isinstance(raw_data, dict):
        packet_dict = dict(raw_data)
    else:
        raise ValueError(f"Expected dictionary or SimulationGroundTruthPacket, got {type(raw_data).__name__}")

    # Validate timestamp
    ts = packet_dict.get("timestamp", 0.0)
    if ts is not None:
        try:
            ts = float(ts)
            _check_finite(ts, "timestamp")
            if ts < 0:
                raise ValueError(f"Negative timestamp {ts} is invalid")
        except (TypeError, ValueError) as err:
            raise ValueError(f"Invalid timestamp '{ts}': {err}") from err

    # Validate frame_id if provided
    frame_id = packet_dict.get("frame_id")
    if frame_id is not None:
        try:
            frame_id = int(frame_id)
            if frame_id < 0:
                raise ValueError(f"Negative frame_id {frame_id} is invalid")
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid frame_id '{frame_id}': {err}") from err

    # Normalize position
    pos = packet_dict.get("position")
    if pos is None:
        # Check flat format
        if "x" in packet_dict and "y" in packet_dict and "z" in packet_dict:
            pos = {
                "x": packet_dict.pop("x"),
                "y": packet_dict.pop("y"),
                "z": packet_dict.pop("z"),
            }
            packet_dict["position"] = pos
        else:
            raise ValueError("Missing required position coordinates (x, y, z)")

    if isinstance(pos, dict):
        if "x" not in pos or "y" not in pos or "z" not in pos:
            raise ValueError("Position dictionary missing 'x', 'y', or 'z'")
        _check_finite(pos["x"], "position.x")
        _check_finite(pos["y"], "position.y")
        _check_finite(pos["z"], "position.z")
    elif isinstance(pos, (list, tuple)) and len(pos) >= 3:
        _check_finite(pos[0], "position[0]")
        _check_finite(pos[1], "position[1]")
        _check_finite(pos[2], "position[2]")
        packet_dict["position"] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}

    # Normalize orientation
    att = packet_dict.get("orientation")
    if att is None:
        if "roll" in packet_dict or "pitch" in packet_dict or "yaw" in packet_dict:
            att = {
                "roll": packet_dict.pop("roll", 0.0),
                "pitch": packet_dict.pop("pitch", 0.0),
                "yaw": packet_dict.pop("yaw", 0.0),
            }
            packet_dict["orientation"] = att

    if isinstance(att, dict):
        _check_finite(att.get("roll", 0.0), "orientation.roll")
        _check_finite(att.get("pitch", 0.0), "orientation.pitch")
        _check_finite(att.get("yaw", 0.0), "orientation.yaw")
    elif isinstance(att, (list, tuple)) and len(att) >= 3:
        _check_finite(att[0], "orientation[0]")
        _check_finite(att[1], "orientation[1]")
        _check_finite(att[2], "orientation[2]")
        packet_dict["orientation"] = {
            "roll": float(att[0]),
            "pitch": float(att[1]),
            "yaw": float(att[2]),
        }

    # Validate LiDAR if present
    lidar = packet_dict.get("lidar")
    if isinstance(lidar, dict):
        for k, v in lidar.items():
            if v is not None:
                _check_finite(v, f"lidar.{k}")

    try:
        return SimulationGroundTruthPacket.model_validate(packet_dict)
    except ValidationError as err:
        raise ValueError(f"P2 ground truth validation failed: {err}") from err
