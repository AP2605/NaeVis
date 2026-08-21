"""P1 Perception API routes."""

from fastapi import APIRouter, HTTPException, status
from app.integrations.p1.service import p1_service
from app.schemas.p1 import P1VisionResult
from app.services.frame_sync import frame_synchronizer

router = APIRouter(prefix="/api/v1/perception", tags=["P1 Perception"])


@router.post(
    "/result",
    status_code=status.HTTP_200_OK,
    summary="Ingest P1 perception / vision result",
    description="Ingest structured perception results from P1 ML module (terrain, segmentation, landmarks, place recognition, etc.).",
)
async def ingest_perception_result(packet: P1VisionResult):
    """Ingest, validate, and synchronize P1 perception result."""
    try:
        frame = await p1_service.process_perception_packet(packet)
        return {
            "status": "success",
            "message": "Perception packet synchronized",
            "frame_id": packet.frame_id,
            "timestamp": packet.timestamp,
            "sync_sources": frame.sync_sources,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest perception packet: {str(exc)}",
        )


@router.get(
    "/latest",
    response_model=P1VisionResult | None,
    summary="Get latest P1 perception result",
    description="Retrieve the most recent structured perception packet received from P1.",
)
def get_latest_perception() -> P1VisionResult | None:
    """Return latest P1 perception packet."""
    return frame_synchronizer._latest_p1
