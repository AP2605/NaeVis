"""P1 Perception Adapter and Normalization Layer.

Normalizes incoming ML / perception payloads from P1 teammates or mock producers
into validated P4 internal representations, rejecting corrupted or non-physical data (NaN, Inf).
"""

import math
from typing import Any
from pydantic import ValidationError

from app.schemas.p1 import (
    Landmark,
    MissionAwareness,
    P1SystemInfo,
    P1VisionResult,
    PlaceRecognition,
    SegmentationResult,
    TerrainMatch,
    TerrainResult,
)
from app.schemas.common import Position3D


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


def normalize_p1_payload(raw_data: Any, is_real: bool = False) -> P1VisionResult:
    """Normalize and validate incoming P1 perception payload.

    Args:
        raw_data: Raw dictionary, JSON, or existing P1VisionResult object.
        is_real: Flag indicating whether this came from a verified real P1 service.

    Returns:
        Validated P1VisionResult model.

    Raises:
        ValueError: If packet structure is malformed, missing required fields, or contains NaN/Inf.
    """
    if isinstance(raw_data, P1VisionResult):
        packet_dict = raw_data.model_dump()
    elif isinstance(raw_data, dict):
        packet_dict = dict(raw_data)
    else:
        raise ValueError(f"Expected dictionary or P1VisionResult, got {type(raw_data).__name__}")

    # Validate frame_id
    frame_id = packet_dict.get("frame_id")
    if frame_id is None:
        raise ValueError("Missing required field 'frame_id' in P1 perception packet")
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

    # Normalize terrain
    terrain_raw = packet_dict.get("terrain")
    if isinstance(terrain_raw, dict):
        t_conf = terrain_raw.get("confidence", 1.0)
        _check_finite(t_conf, "terrain.confidence")
        if t_conf is not None and not (0.0 <= float(t_conf) <= 1.0):
            raise ValueError(f"Terrain confidence {t_conf} out of bounds [0.0, 1.0]")
        t_roughness = terrain_raw.get("roughness")
        _check_finite(t_roughness, "terrain.roughness")

    # Normalize landmarks
    landmarks_raw = packet_dict.get("landmarks", [])
    if isinstance(landmarks_raw, list):
        for idx, lm in enumerate(landmarks_raw):
            if isinstance(lm, dict):
                lm_conf = lm.get("confidence", 1.0)
                _check_finite(lm_conf, f"landmarks[{idx}].confidence")
                if lm_conf is not None and not (0.0 <= float(lm_conf) <= 1.0):
                    raise ValueError(f"Landmark [{idx}] confidence {lm_conf} out of bounds [0.0, 1.0]")

                # Check bounding box
                bbox = lm.get("bbox")
                if bbox is not None:
                    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                        raise ValueError(f"Landmark [{idx}] bbox must have 4 coordinates [xmin, ymin, xmax, ymax]")
                    for c in bbox:
                        _check_finite(float(c), f"landmarks[{idx}].bbox coordinate")

                # Check relative position
                rel_pos = lm.get("estimated_relative_pos")
                if isinstance(rel_pos, dict):
                    _check_finite(rel_pos.get("x"), f"landmarks[{idx}].relative_pos.x")
                    _check_finite(rel_pos.get("y"), f"landmarks[{idx}].relative_pos.y")
                    _check_finite(rel_pos.get("z"), f"landmarks[{idx}].relative_pos.z")

    # Normalize visual localization hint
    hint_raw = packet_dict.get("visual_localization_hint")
    if isinstance(hint_raw, dict):
        hint_conf = hint_raw.get("hint_confidence")
        _check_finite(hint_conf, "visual_localization_hint.hint_confidence")
        sug_corr = hint_raw.get("suggested_correction")
        if isinstance(sug_corr, dict):
            _check_finite(sug_corr.get("x"), "visual_localization_hint.suggested_correction.x")
            _check_finite(sug_corr.get("y"), "visual_localization_hint.suggested_correction.y")
            _check_finite(sug_corr.get("z"), "visual_localization_hint.suggested_correction.z")

    try:
        return P1VisionResult.model_validate(packet_dict)
    except ValidationError as err:
        raise ValueError(f"P1 perception validation failed: {err}") from err
