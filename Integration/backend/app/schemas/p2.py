"""P2 Simulation Ground Truth schemas."""

from typing import Any
from pydantic import BaseModel, Field, model_validator
from app.schemas.common import Position3D, Orientation3D, LidarData, CameraReference


class SimulationGroundTruthPacket(BaseModel):
    """Ground truth telemetry packet provided by P2 (Blender Simulation).

    P2 ground truth represents absolute true simulation state, used for
    visualization, evaluation, and benchmark comparison against P3 navigation estimates.
    """

    timestamp: float = Field(default=0.0, description="Simulation epoch timestamp in seconds")
    frame_id: int | None = Field(default=None, description="Simulation frame index identifier")
    position: Position3D = Field(..., description="Ground truth position in meters (Blender coordinate frame)")
    orientation: Orientation3D = Field(
        default_factory=Orientation3D,
        description="Ground truth attitude in degrees (roll, pitch, yaw)"
    )
    velocity: Position3D | None = Field(default=None, description="Ground truth linear velocity in m/s")
    lidar: LidarData | None = Field(default=None, description="Simulated LiDAR range measurements in meters")
    camera: CameraReference | None = Field(default=None, description="Camera frame metadata and image path reference")

    @model_validator(mode="before")
    @classmethod
    def parse_ground_truth_packet(cls, data: Any) -> Any:
        """Parse ground_truth dictionary if provided as single nested object."""
        if isinstance(data, dict):
            data = dict(data)
            if "timestamp" not in data or data["timestamp"] is None:
                data["timestamp"] = 0.0
            if "ground_truth" in data and isinstance(data["ground_truth"], dict):
                gt = data.pop("ground_truth")
                if "position" in gt and "orientation" in gt:
                    data["position"] = gt["position"]
                    data["orientation"] = gt["orientation"]
                else:
                    data["position"] = {
                        "x": float(gt.get("x", 0.0)),
                        "y": float(gt.get("y", 0.0)),
                        "z": float(gt.get("z", 0.0)),
                    }
                    data["orientation"] = {
                        "roll": float(gt.get("roll", 0.0)),
                        "pitch": float(gt.get("pitch", 0.0)),
                        "yaw": float(gt.get("yaw", 0.0)),
                    }
                if "velocity" in gt and "velocity" not in data:
                    data["velocity"] = gt["velocity"]
        return data

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
