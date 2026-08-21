"""Mission Management REST API Routes."""

from fastapi import APIRouter, HTTPException, status
import logging

from app.schemas.mission import (
    MissionCreate,
    MissionResponse,
    MissionUpdate,
)
from app.services.mission_service import mission_service

logger = logging.getLogger("sih_navis.api.missions")

router = APIRouter(
    prefix="/api/v1/missions",
    tags=["Missions"],
)


@router.post(
    "",
    response_model=MissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new mission",
    description="Define source, destination, and arbitrary waypoints in Blender simulation coordinates.",
)
async def create_mission(mission_in: MissionCreate) -> MissionResponse:
    """Create a new mission definition."""
    try:
        return await mission_service.create_mission(mission_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        logger.error("Error creating mission: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create mission")


@router.get(
    "",
    response_model=list[MissionResponse],
    status_code=status.HTTP_200_OK,
    summary="List all missions",
    description="Retrieve all defined missions in reverse chronological order.",
)
def list_missions(limit: int = 50, offset: int = 0) -> list[MissionResponse]:
    """Retrieve list of missions."""
    return mission_service.list_missions(limit=limit, offset=offset)


@router.get(
    "/active/current",
    response_model=MissionResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Get active or latest mission",
    description="Fetch the currently active mission or the most recent mission with its execution progress.",
)
def get_active_mission() -> MissionResponse | None:
    """Fetch active or latest mission."""
    return mission_service.get_active_mission()


@router.get(
    "/{mission_id}",
    response_model=MissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get mission details",
    description="Fetch a specific mission by UUID including ordered waypoints and current execution progress.",
)
def get_mission(mission_id: str) -> MissionResponse:
    """Fetch mission by UUID."""
    mission = mission_service.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    return mission


@router.put(
    "/{mission_id}",
    response_model=MissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update mission",
    description="Modify mission name, source, destination, or waypoints (only allowed in non-active states).",
)
async def update_mission(mission_id: str, update_in: MissionUpdate) -> MissionResponse:
    """Update mission fields."""
    try:
        return await mission_service.update_mission(mission_id, update_in)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception as exc:
        logger.error("Error updating mission: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update mission")


@router.delete(
    "/{mission_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete mission",
    description="Remove a mission and its waypoints.",
)
async def delete_mission(mission_id: str) -> dict[str, str]:
    """Delete mission."""
    try:
        deleted = await mission_service.delete_mission(mission_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
        return {"status": "deleted", "mission_id": mission_id}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{mission_id}/start",
    response_model=MissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Start mission",
    description="Transmit validated mission to P3 navigation and transition to ACTIVE state.",
)
async def start_mission(mission_id: str) -> MissionResponse:
    """Start mission execution."""
    try:
        return await mission_service.start_mission(mission_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{mission_id}/pause",
    response_model=MissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause mission",
    description="Pause currently executing active mission.",
)
async def pause_mission(mission_id: str) -> MissionResponse:
    """Pause mission."""
    try:
        return await mission_service.pause_mission(mission_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{mission_id}/resume",
    response_model=MissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume mission",
    description="Resume a paused mission back to ACTIVE state.",
)
async def resume_mission(mission_id: str) -> MissionResponse:
    """Resume mission."""
    try:
        return await mission_service.resume_mission(mission_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{mission_id}/cancel",
    response_model=MissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel mission",
    description="Cancel active or paused mission.",
)
async def cancel_mission(mission_id: str) -> MissionResponse:
    """Cancel mission."""
    try:
        return await mission_service.cancel_mission(mission_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission '{mission_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
