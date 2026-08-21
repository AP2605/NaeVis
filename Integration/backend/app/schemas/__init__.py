"""Schema definitions for SIH-NAVIS integration backend."""

from app.schemas.common import (
    CameraReference,
    LidarData,
    Orientation3D,
    Position3D,
    TrackingStateEnum,
    Velocity3D,
)
from app.schemas.integrated import IntegratedFrame, IntegratedState
from app.schemas.p1 import (
    Landmark,
    MissionAwareness,
    P1SystemInfo,
    P1VisionResult,
    PlaceRecognition,
    SegmentationResult,
    TerrainMatch,
    TerrainResult,
    VisualLocalizationHint,
)
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import EstimatedPose, NavigationStatePacket
from app.schemas.telemetry import Telemetry
from app.schemas.websocket import (
    GroundTruthEvent,
    IntegratedStateEvent,
    NavigationEvent,
    PerceptionEvent,
    TelemetryEvent,
    WebSocketClientMessage,
    WebSocketEvent,
)

__all__ = [
    "Position3D",
    "Orientation3D",
    "Velocity3D",
    "LidarData",
    "CameraReference",
    "TrackingStateEnum",
    "Telemetry",
    "SimulationGroundTruthPacket",
    "EstimatedPose",
    "NavigationStatePacket",
    "TerrainResult",
    "Landmark",
    "SegmentationResult",
    "PlaceRecognition",
    "TerrainMatch",
    "MissionAwareness",
    "VisualLocalizationHint",
    "P1SystemInfo",
    "P1VisionResult",
    "IntegratedFrame",
    "IntegratedState",
    "WebSocketEvent",
    "TelemetryEvent",
    "IntegratedStateEvent",
    "GroundTruthEvent",
    "NavigationEvent",
    "PerceptionEvent",
    "WebSocketClientMessage",
]
