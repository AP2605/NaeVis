"""P1 ML / Perception schemas."""

from pydantic import BaseModel, Field
from app.schemas.common import Position3D


class TerrainResult(BaseModel):
    """Terrain classification result from P1."""

    terrain_type: str = Field(
        default="urban",
        description="Classified dominant terrain category (e.g. urban, forest, water, barren, runway)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence score [0.0 - 1.0]",
    )
    roughness: float | None = Field(
        default=None,
        description="Estimated terrain surface roughness or landing safety coefficient",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Detected terrain sub-features (e.g. ['asphalt_road', 'vegetation', 'flat_ground'])",
    )


class Landmark(BaseModel):
    """Detected visual or topological landmark."""

    landmark_id: str | int = Field(..., description="Unique identifier for the landmark")
    label: str = Field(..., description="Semantic label (e.g. building_corner, road_intersection, tower)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Detection confidence score")
    bbox: list[float] | None = Field(
        default=None,
        description="Bounding box [x_min, y_min, x_max, y_max] in normalized or pixel coordinates",
    )
    estimated_relative_pos: Position3D | None = Field(
        default=None,
        description="Estimated relative 3D coordinate vector from drone to landmark in meters",
    )


class SegmentationResult(BaseModel):
    """Semantic segmentation summary and mask reference."""

    classes: list[str] = Field(
        default_factory=list,
        description="List of detected semantic classes in frame",
    )
    mask_path: str | None = Field(
        default=None,
        description="File path or URI to the rendered/saved PNG segmentation mask",
    )
    coverage_percentages: dict[str, float] = Field(
        default_factory=dict,
        description="Class coverage distribution percentages across the frame",
    )


class PlaceRecognition(BaseModel):
    """Visual place recognition / topological loop closure match."""

    match_found: bool = Field(default=False, description="Whether a visual database match was recognized")
    location_id: str | None = Field(default=None, description="Recognized location node ID")
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Visual descriptor similarity score")
    reference_coordinates: Position3D | None = Field(
        default=None,
        description="Known reference geo-position of the matched location",
    )


class TerrainMatch(BaseModel):
    """Terrain elevation or ortho-map matching result."""

    matched: bool = Field(default=False, description="Whether map matching succeeded")
    elevation_estimate: float | None = Field(default=None, description="Estimated terrain elevation AGL/MSL in meters")
    map_tile_id: str | None = Field(default=None, description="Associated satellite/DEM map tile identifier")
    correlation_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Map correlation quality score")


class MissionAwareness(BaseModel):
    """High-level mission awareness and safety assessment."""

    threat_detected: bool = Field(default=False, description="Whether an obstacle, no-fly zone, or threat is present")
    landing_zone_viable: bool = Field(default=True, description="Whether the area below is viable for emergency landing")
    notes: str | None = Field(default=None, description="Mission notes or warning messages")


class VisualLocalizationHint(BaseModel):
    """Visual localization correction hint for P3 fusion."""

    suggested_correction: Position3D | None = Field(
        default=None,
        description="Suggested position delta/correction vector in meters",
    )
    uncertainty_radius: float | None = Field(
        default=None,
        description="Radius of uncertainty around the hint in meters",
    )
    hint_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence of visual localization hint [0.0 - 1.0]",
    )


class P1SystemInfo(BaseModel):
    """P1 ML perception pipeline system diagnostics."""

    model_version: str | None = Field(default="v1.0", description="Perception neural network model version")
    inference_time_ms: float = Field(default=0.0, description="Neural network forward inference latency in ms")
    device: str | None = Field(default="cuda:0", description="Compute device used for inference")
    gpu_utilization_pct: float | None = Field(default=None, description="GPU utilization percentage")


class P1VisionResult(BaseModel):
    """Complete perception and ML vision output packet provided by P1.

    Contains terrain classification, semantic segmentation, landmarks,
    place recognition, terrain matching, mission awareness, and system diagnostics.
    """

    frame_id: int = Field(..., description="Frame index matching simulation/navigation frame")
    timestamp: float = Field(..., description="Timestamp in seconds")
    terrain: TerrainResult = Field(default_factory=TerrainResult)
    segmentation: SegmentationResult = Field(default_factory=SegmentationResult)
    landmarks: list[Landmark] = Field(default_factory=list)
    place_recognition: PlaceRecognition | None = Field(default=None)
    terrain_match: TerrainMatch | None = Field(default=None)
    mission_awareness: MissionAwareness | None = Field(default=None)
    visual_localization_hint: VisualLocalizationHint | None = Field(default=None)
    system: P1SystemInfo | None = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "example": {
                "frame_id": 125,
                "timestamp": 4.166,
                "terrain": {
                    "terrain_type": "urban",
                    "confidence": 0.95,
                    "roughness": 0.12,
                    "features": ["building", "road", "vehicle"],
                },
                "segmentation": {
                    "classes": ["building", "road", "vegetation"],
                    "mask_path": "masks/seg_frame_0125.png",
                    "coverage_percentages": {
                        "building": 45.2,
                        "road": 30.8,
                        "vegetation": 24.0,
                    },
                },
                "landmarks": [
                    {
                        "landmark_id": "LM_101",
                        "label": "building_corner",
                        "confidence": 0.92,
                        "bbox": [100.0, 150.0, 220.0, 280.0],
                        "estimated_relative_pos": {"x": 15.2, "y": 3.4, "z": -8.1},
                    }
                ],
                "place_recognition": {
                    "match_found": True,
                    "location_id": "LOC_ALPHA_4",
                    "similarity_score": 0.88,
                    "reference_coordinates": {"x": 100.0, "y": 50.0, "z": 30.0},
                },
                "terrain_match": {
                    "matched": True,
                    "elevation_estimate": 31.5,
                    "map_tile_id": "tile_12_45",
                    "correlation_score": 0.91,
                },
                "mission_awareness": {
                    "threat_detected": False,
                    "landing_zone_viable": True,
                    "notes": "Clear approach path",
                },
                "visual_localization_hint": {
                    "suggested_correction": {"x": 0.15, "y": -0.10, "z": 0.05},
                    "uncertainty_radius": 0.5,
                    "hint_confidence": 0.85,
                },
                "system": {
                    "model_version": "yolo-seg-v8-drone",
                    "inference_time_ms": 32.4,
                    "device": "cuda:0",
                    "gpu_utilization_pct": 65.0,
                },
            }
        }
    }
