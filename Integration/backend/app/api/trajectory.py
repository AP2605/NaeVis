"""Trajectory Data REST API Routes."""

from fastapi import APIRouter, Query, status
import logging

from app.repositories.trajectory_repository import trajectory_repository
from app.schemas.trajectory import TrajectoryResponse

logger = logging.getLogger("sih_navis.api.trajectory")

router = APIRouter(
    prefix="/api/v1/trajectory",
    tags=["Trajectory"],
)


@router.get(
    "",
    response_model=TrajectoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get trajectory points",
    description="Retrieve synchronized Ground Truth and Estimated Pose trajectory history points.",
)
def get_trajectory(
    limit: int = Query(500, ge=1, le=5000, description="Maximum number of historical points"),
    mission_id: str | None = Query(None, description="Optional mission filter"),
) -> TrajectoryResponse:
    """Retrieve ground truth and estimated trajectory point series."""
    return trajectory_repository.get_trajectory(limit=limit, mission_id=mission_id)
