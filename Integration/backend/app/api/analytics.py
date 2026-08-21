"""Analytics and Navigation Evaluation REST API Routes."""

from fastapi import APIRouter, Query, status
import logging

from app.schemas.analytics import AnalyticsResponse
from app.services.analytics_service import analytics_service

logger = logging.getLogger("sih_navis.api.analytics")

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Analytics"],
)


@router.get(
    "/current",
    response_model=AnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current analytics and evaluation metrics",
    description="Returns real-time 3D localization error, ATE, RPE, drift, and attitude angular errors.",
)
def get_current_analytics(
    limit: int = Query(500, ge=1, le=2000, description="Max trajectory history samples to evaluate")
) -> AnalyticsResponse:
    """Retrieve computed analytics."""
    return analytics_service.compute_metrics(limit=limit)


@router.get(
    "/metrics",
    response_model=AnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated navigation metrics",
    description="Alias for current evaluation metrics over all synchronized samples.",
)
def get_metrics_summary(
    limit: int = Query(500, ge=1, le=2000, description="Max trajectory samples to evaluate")
) -> AnalyticsResponse:
    """Retrieve summary metrics."""
    return analytics_service.compute_metrics(limit=limit)
