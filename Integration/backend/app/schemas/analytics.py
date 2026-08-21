"""Analytics and navigation evaluation metric schemas."""

from pydantic import BaseModel, Field


class LocalizationErrorMetric(BaseModel):
    """Euclidean and per-axis localization error in meters."""

    current: float | None = Field(default=None, description="Latest 3D Euclidean error in meters")
    mean: float | None = Field(default=None, description="Mean 3D Euclidean error across history in meters")
    rmse: float | None = Field(default=None, description="Root Mean Square Error across history in meters")
    maximum: float | None = Field(default=None, description="Peak Euclidean error across history in meters")
    dx: float | None = Field(default=None, description="Current X-axis error (x_est - x_gt) in meters")
    dy: float | None = Field(default=None, description="Current Y-axis error (y_est - y_gt) in meters")
    dz: float | None = Field(default=None, description="Current Z-axis / altitude error (z_est - z_gt) in meters")


class AteMetric(BaseModel):
    """Absolute Trajectory Error (ATE) across synchronized trajectory points."""

    mean: float | None = Field(default=None, description="Mean ATE in meters")
    rmse: float | None = Field(default=None, description="RMSE of ATE in meters")
    maximum: float | None = Field(default=None, description="Maximum ATE in meters")
    sample_count: int = Field(default=0, description="Number of synchronized samples used")


class RpeMetric(BaseModel):
    """Relative Pose Error (RPE) measuring drift rate over consecutive steps."""

    mean: float | None = Field(default=None, description="Mean translational RPE in meters")
    rmse: float | None = Field(default=None, description="RMSE of translational RPE in meters")
    sample_count: int = Field(default=0, description="Number of consecutive step pairs used")


class DriftMetric(BaseModel):
    """Accumulated trajectory drift relative to total ground truth travel distance."""

    absolute_meters: float | None = Field(default=None, description="Final position error in meters")
    percentage: float | None = Field(default=None, description="Drift as percentage of total traveled distance")
    traveled_distance_m: float | None = Field(default=None, description="Total ground truth traveled distance in meters")


class OrientationErrorMetric(BaseModel):
    """Attitude and heading angular errors with normalized wrap-around in degrees."""

    roll: float | None = Field(default=None, description="Roll error in degrees")
    pitch: float | None = Field(default=None, description="Pitch error in degrees")
    yaw: float | None = Field(default=None, description="Normalized yaw heading error [-180, 180] in degrees")


class AnalyticsResponse(BaseModel):
    """Full consolidated analytics evaluation response."""

    localization_error: LocalizationErrorMetric
    ate: AteMetric
    rpe: RpeMetric
    drift: DriftMetric
    orientation_error: OrientationErrorMetric
    synchronization_status: str = Field(default="INSUFFICIENT DATA", description="Sync health: SYNCED, PARTIAL, STALE, MISSING, INSUFFICIENT DATA")
    sample_count: int = Field(default=0, description="Total synchronized frame count evaluated")
    timestamp: float = Field(default=0.0, description="Evaluation timestamp")
