"""P3 Navigation and SLAM Adapter Layer.

Normalizes incoming navigation state estimation packets from P3 teammates,
VIO/SLAM pipelines, or mock producers into validated P4 internal representations.
"""

import math
from typing import Any
from pydantic import ValidationError

from app.schemas.p3 import EstimatedPose, NavigationStatePacket
from app.schemas.common import Velocity3D


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


def normalize_p3_navigation(raw_data: Any, is_real: bool = False) -> NavigationStatePacket:
    """Normalize and validate incoming P3 navigation state packet.

    Args:
        raw_data: Raw dictionary or NavigationStatePacket instance.
        is_real: Flag indicating whether packet is from real P3 navigation service.

    Returns:
        Validated NavigationStatePacket model.

    Raises:
        ValueError: If packet structure is malformed, missing required fields, or contains NaN/Inf.
    """
    if isinstance(raw_data, NavigationStatePacket):
        packet_dict = raw_data.model_dump()
    elif isinstance(raw_data, dict):
        packet_dict = dict(raw_data)
    else:
        raise ValueError(f"Expected dictionary or NavigationStatePacket, got {type(raw_data).__name__}")

    # Validate frame_id
    frame_id = packet_dict.get("frame_id")
    if frame_id is None:
        raise ValueError("Missing required field 'frame_id' in P3 navigation packet")
    try:
        frame_id = int(frame_id)
        if frame_id < 0:
            raise ValueError(f"Negative frame_id {frame_id} is invalid")
    except (ValueError, TypeError) as err:
        raise ValueError(f"Invalid frame_id '{frame_id}': {err}") from err

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

    # Normalize estimated_pose
    pose = packet_dict.get("estimated_pose")
    if pose is None:
        # Check flat format
        if "x" in packet_dict and "y" in packet_dict and "z" in packet_dict:
            pose = {
                "x": packet_dict.pop("x"),
                "y": packet_dict.pop("y"),
                "z": packet_dict.pop("z"),
                "roll": packet_dict.pop("roll", 0.0),
                "pitch": packet_dict.pop("pitch", 0.0),
                "yaw": packet_dict.pop("yaw", 0.0),
            }
            packet_dict["estimated_pose"] = pose
        else:
            raise ValueError("Missing required 'estimated_pose' or (x, y, z) in navigation packet")

    if isinstance(pose, dict):
        if "x" not in pose or "y" not in pose or "z" not in pose:
            raise ValueError("estimated_pose dictionary missing 'x', 'y', or 'z'")
        _check_finite(pose["x"], "estimated_pose.x")
        _check_finite(pose["y"], "estimated_pose.y")
        _check_finite(pose["z"], "estimated_pose.z")
        _check_finite(pose.get("roll", 0.0), "estimated_pose.roll")
        _check_finite(pose.get("pitch", 0.0), "estimated_pose.pitch")
        _check_finite(pose.get("yaw", 0.0), "estimated_pose.yaw")
    elif isinstance(pose, (list, tuple)) and len(pose) >= 3:
        _check_finite(pose[0], "estimated_pose[0]")
        _check_finite(pose[1], "estimated_pose[1]")
        _check_finite(pose[2], "estimated_pose[2]")
        roll = float(pose[3]) if len(pose) > 3 else 0.0
        pitch = float(pose[4]) if len(pose) > 4 else 0.0
        yaw = float(pose[5]) if len(pose) > 5 else 0.0
        packet_dict["estimated_pose"] = {
            "x": float(pose[0]),
            "y": float(pose[1]),
            "z": float(pose[2]),
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
        }

    # Normalize velocity
    vel = packet_dict.get("velocity")
    if isinstance(vel, dict):
        _check_finite(vel.get("x", 0.0), "velocity.x")
        _check_finite(vel.get("y", 0.0), "velocity.y")
        _check_finite(vel.get("z", 0.0), "velocity.z")
    elif isinstance(vel, (list, tuple)) and len(vel) >= 3:
        _check_finite(vel[0], "velocity[0]")
        _check_finite(vel[1], "velocity[1]")
        _check_finite(vel[2], "velocity[2]")
        packet_dict["velocity"] = {"x": float(vel[0]), "y": float(vel[1]), "z": float(vel[2])}

    # Validate confidence
    conf = packet_dict.get("confidence", 1.0)
    _check_finite(conf, "confidence")
    if conf is not None:
        c_val = float(conf)
        if not (0.0 <= c_val <= 1.0):
            # clamp if slightly outside or raise
            if c_val < 0.0 or c_val > 1.05:
                raise ValueError(f"Confidence score {c_val} out of valid range [0.0, 1.0]")
            packet_dict["confidence"] = max(0.0, min(1.0, c_val))

    # Validate processing_time_ms
    proc_time = packet_dict.get("processing_time_ms")
    if proc_time is not None:
        _check_finite(proc_time, "processing_time_ms")

    try:
        return NavigationStatePacket.model_validate(packet_dict)
    except ValidationError as err:
        raise ValueError(f"P3 navigation validation failed: {err}") from err
