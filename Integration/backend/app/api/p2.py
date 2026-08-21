"""P2 Simulation Ground Truth API routes."""

from fastapi import APIRouter, HTTPException, status
from app.integrations.p2.service import p2_service
from app.schemas.p2 import SimulationGroundTruthPacket
from app.services.frame_sync import frame_synchronizer

router = APIRouter(prefix="/api/v1/simulation", tags=["P2 Simulation"])


@router.post(
    "/ground-truth",
    status_code=status.HTTP_200_OK,
    summary="Ingest P2 simulation ground truth",
    description="Ingest true 6-DoF position, orientation, LiDAR, and camera metadata from Blender simulation.",
)
async def ingest_ground_truth(packet: SimulationGroundTruthPacket):
    """Ingest, validate, and synchronize P2 simulation ground truth."""
    try:
        frame = await p2_service.process_ground_truth_packet(packet)
        return {
            "status": "success",
            "message": "Ground truth packet synchronized",
            "frame_id": frame.frame_id,
            "timestamp": packet.timestamp,
            "sync_sources": frame.sync_sources,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest ground truth packet: {str(exc)}",
        )


@router.get(
    "/ground-truth/latest",
    response_model=SimulationGroundTruthPacket | None,
    summary="Get latest P2 ground truth",
    description="Retrieve the most recent ground truth packet received from P2 simulation.",
)
def get_latest_ground_truth() -> SimulationGroundTruthPacket | None:
    """Return latest P2 simulation ground truth packet."""
    return frame_synchronizer._latest_p2
