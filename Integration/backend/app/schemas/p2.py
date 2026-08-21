"""P2 Simulation Ground Truth schemas."""

from pydantic import BaseModel, Field, model_validator
from app.schemas.common import Position3D, Orientation3D, LidarData, CameraReference


class SimulationGroundTruthPacket(BaseModel):
    """Ground truth telemetry packet provided by P2 (Blender Simulation).

    P2 ground truth represents absolute true simulation state, used for
    visualization, evaluation, and benchmark comparison against P3 navigation estimates.
    """

    timestamp: float = Field(..., description="Simulation epoch timestamp in seconds")
    frame_id: int | None = Field(default=None, description="Simulation frame index identifier")
    position: Position3D = Field(..., description="Ground truth position in meters (Blender coordinate frame)")
    orientation: Orientation3D = Field(..., description="Ground truth attitude in degrees (roll, pitch, yaw)")
    lidar: LidarData | None = Field(default=None, description="Simulated LiDAR range measurements in meters")
    camera: CameraReference | None = Field(default=None, description="Camera frame metadata and image path reference")

    @model_validator(mode="after")
    def populate_frame_id_from_camera(self) -> "SimulationGroundTruthPacket":
        """Extract frame_id from camera reference if not provided at top-level."""
        if self.frame_id is None and self.camera is not None and self.camera.frame_id is not None:
            self.frame_id = self.camera.frame_id
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": 1723987200.125,
                "frame_id": 125,
                "position": {
                    "x": 100.25,
                    "y": 52.40,
                    "z": 31.70,
                },
                "orientation": {
                    "roll": 4.58,
                    "pitch": -1.72,
                    "yaw": 87.09,
                },
                "lidar": {
                    "front": 18.40,
                    "front_left": 22.10,
                    "front_right": 15.70,
                    "bottom": 12.70,
                },
                "camera": {
                    "frame_id": 125,
                    "image_path": "frames/frame_0125.png",
                },
            }
        }
    }
