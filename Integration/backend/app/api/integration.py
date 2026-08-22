"""Unified Integration state and frame query API routes."""

from fastapi import APIRouter, HTTPException, Query, status
from app.schemas.integrated import IntegratedFrame, IntegratedState
from app.services.camera_service import camera_service
from app.services.frame_sync import frame_synchronizer
from app.services.integration_service import integration_service

router = APIRouter(prefix="/api/v1/integration", tags=["Integration State"])


@router.get(
    "/state",
    response_model=IntegratedState,
    summary="Get current integrated state",
    description="Retrieve the latest composite system state across P1, P2, and P3 modules.",
)
def get_integrated_state() -> IntegratedState:
    """Return unified composite state."""
    return integration_service.get_current_integrated_state()


@router.get(
    "/frames",
    response_model=list[IntegratedFrame],
    summary="Get recent synchronized frames",
    description="Retrieve recent integrated frames stored in the ring buffer.",
)
def get_recent_frames(
    limit: int = Query(default=50, ge=1, le=500, description="Max number of frames to return"),
) -> list[IntegratedFrame]:
    """Return list of recent synchronized frames."""
    return frame_synchronizer.get_recent_frames(limit=limit)


@router.get(
    "/frames/{frame_id}",
    response_model=IntegratedFrame,
    summary="Get synchronized frame by frame_id",
    description="Retrieve a specific synchronized multi-module frame by its frame index.",
)
def get_frame_by_id(frame_id: int) -> IntegratedFrame:
    """Return single integrated frame."""
    frame = frame_synchronizer.get_frame(frame_id)
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Frame {frame_id} not found in synchronization buffer",
        )
    return frame


@router.post(
    "/reset",
    summary="Reset integration buffers",
    description="Clear synchronization buffer and reset all stream counters.",
)
def reset_integration_state():
    """Reset synchronizer buffer."""
    frame_synchronizer.reset()
    return {"status": "success", "message": "Integration buffers and counters reset"}


@router.get(
    "/camera/stats",
    summary="Get camera streaming statistics",
    description="Retrieve camera FPS, viewer count, producer status, and latency.",
)
def get_camera_stats():
    """Return camera stream diagnostics."""
    return camera_service.get_stats()


@router.get(
    "/health",
    summary="Get integration sources health",
    description="Retrieve explicit operational states (CONNECTED, MOCK, STALE, DISCONNECTED) for P1, P2, P3, and Camera.",
)
def get_integration_health():
    """Return health metrics and connection states for all sources."""
    return frame_synchronizer.get_source_health()
