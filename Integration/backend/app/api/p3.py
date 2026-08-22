"""P3 Navigation State API routes."""

from fastapi import APIRouter, Header, HTTPException, Query, status
from app.config import settings
from app.integrations.p3.service import p3_service
from app.schemas.p3 import NavigationStatePacket
from app.services.frame_sync import frame_synchronizer

router = APIRouter(prefix="/api/v1/navigation", tags=["P3 Navigation"])


@router.post(
    "/state",
    status_code=status.HTTP_200_OK,
    summary="Ingest P3 navigation state estimation",
    description="Ingest estimated 6-DoF pose, 3D velocity vector, tracking health, confidence, and processing latency from P3 navigation engine.",
)
async def ingest_navigation_state(
    packet: NavigationStatePacket,
    source: str = Query(
        default="auto",
        description="Source mode: 'real' for verified teammate stream, 'mock' for synthetic, 'auto' for config-based",
    ),
    x_source_type: str | None = Header(default=None, alias="X-Source-Type"),
):
    """Ingest, validate, and synchronize P3 navigation state."""
    is_real = False
    if source.lower() == "real" or (x_source_type and x_source_type.lower() == "real"):
        is_real = True
    elif settings.SOURCE_MODE.upper() == "REAL":
        is_real = True

    try:
        frame = await p3_service.process_navigation_packet(packet, is_real=is_real)
        return {
            "status": "success",
            "message": "Navigation state packet synchronized",
            "frame_id": packet.frame_id,
            "timestamp": packet.timestamp,
            "sync_sources": frame.sync_sources,
            "is_real": is_real,
        }
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation failed for navigation packet: {str(val_err)}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest navigation packet: {str(exc)}",
        )


@router.get(
    "/state/latest",
    response_model=NavigationStatePacket | None,
    summary="Get latest P3 navigation state",
    description="Retrieve the most recent navigation estimation packet received from P3.",
)
def get_latest_navigation_state() -> NavigationStatePacket | None:
    """Return latest P3 navigation state packet."""
    return frame_synchronizer._latest_p3
