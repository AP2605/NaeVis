"""Trajectory schemas for ground truth, navigation estimates, and historical paths."""

from pydantic import BaseModel, Field


class TrajectoryPoint(BaseModel):
    """Individual 3D trajectory sample with attitude and timing information."""

    frame_id: int = Field(..., description="Frame sequence number")
    timestamp: float = Field(..., description="Simulation or epoch timestamp in seconds")
    x: float = Field(..., description="X coordinate in Blender simulation frame")
    y: float = Field(..., description="Y coordinate in Blender simulation frame")
    z: float = Field(..., description="Z coordinate / altitude in Blender simulation frame")
    roll: float = Field(default=0.0, description="Roll angle in degrees")
    pitch: float = Field(default=0.0, description="Pitch angle in degrees")
    yaw: float = Field(default=0.0, description="Yaw heading in degrees")


class TrajectorySyncPair(BaseModel):
    """Synchronized ground truth and estimated pose sample pair."""

    frame_id: int
    timestamp: float
    ground_truth: TrajectoryPoint | None = None
    estimated: TrajectoryPoint | None = None
    error_3d: float | None = Field(default=None, description="Euclidean distance error in meters")


class TrajectoryResponse(BaseModel):
    """Trajectory historical endpoints response."""

    mission_id: str | None = None
    ground_truth: list[TrajectoryPoint] = Field(default_factory=list, description="Ground truth trajectory series")
    estimated: list[TrajectoryPoint] = Field(default_factory=list, description="Estimated pose trajectory series")
    sample_count: int = Field(..., description="Number of synchronized trajectory points")
