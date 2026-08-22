"""Unified Integrated State and Synchronization schemas."""

from typing import Any
from pydantic import BaseModel, Field
from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket
from app.schemas.common import CameraReference


class IntegratedFrame(BaseModel):
    """Synchronized single-frame container associating P1, P2, and P3 outputs."""

    frame_id: int = Field(..., description="Frame index")
    timestamp: float = Field(..., description="Associated simulation timestamp in seconds")
    ground_truth: SimulationGroundTruthPacket | None = Field(
        default=None,
        description="P2 Ground Truth simulation state",
    )
    navigation: NavigationStatePacket | None = Field(
        default=None,
        description="P3 Estimated navigation state",
    )
    perception: P1VisionResult | None = Field(
        default=None,
        description="P1 ML / Perception output",
    )
    camera_available: bool = Field(
        default=False,
        description="Whether a camera frame was received for this frame_id",
    )
    sync_sources: list[str] = Field(
        default_factory=list,
        description="Sources currently attached to this frame (e.g. ['p1', 'p2', 'p3'])",
    )
    created_at: float = Field(
        default=0.0,
        description="P4 ingestion epoch timestamp",
    )


class SourceHealth(BaseModel):
    """Source health and operational state metrics."""

    state: str = Field(
        default="DISCONNECTED",
        description="Operational state: CONNECTED | MOCK | STALE | DISCONNECTED | ERROR",
    )
    is_real: bool = Field(
        default=False,
        description="Whether source is receiving verified real teammate hardware/network data",
    )
    last_packet_time: float = Field(
        default=0.0,
        description="Epoch timestamp of most recent packet received",
    )
    packet_count: int = Field(
        default=0,
        description="Total number of packets received",
    )
    rate_hz: float = Field(
        default=0.0,
        description="Current measured ingestion rate in Hz",
    )
    last_frame_id: int | None = Field(
        default=None,
        description="Most recent frame index received",
    )
    age_seconds: float | None = Field(
        default=None,
        description="Elapsed seconds since last received packet",
    )


class IntegratedState(BaseModel):
    """Latest composite system state combining latest available P1, P2, and P3 data."""

    current_frame_id: int | None = Field(
        default=None,
        description="Highest frame_id received across active modules",
    )
    latest_timestamp: float | None = Field(
        default=None,
        description="Timestamp of the most recent update in seconds",
    )
    ground_truth: SimulationGroundTruthPacket | None = Field(
        default=None,
        description="Most recent P2 ground truth packet",
    )
    navigation: NavigationStatePacket | None = Field(
        default=None,
        description="Most recent P3 navigation state packet",
    )
    perception: P1VisionResult | None = Field(
        default=None,
        description="Most recent P1 perception result packet",
    )
    latest_camera: CameraReference | None = Field(
        default=None,
        description="Most recent camera frame reference metadata",
    )
    sync_status: dict[str, Any] = Field(
        default_factory=dict,
        description="Synchronization diagnostics (packet rates, frame skew, source counts)",
    )
    system_status: dict[str, Any] = Field(
        default_factory=dict,
        description="Overall integration hub status",
    )
    source_health: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed per-source health status (P1, P2, P3, Camera)",
    )
