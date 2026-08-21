"""Health check API endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Health check",
    description="Verify that the integration backend is active and responsive.",
)
@router.get(
    "/api/v1/health",
    summary="Health check (v1)",
    description="Verify that the integration backend is active and responsive.",
)
def read_health():
    """Return health status."""
    return {"status": "healthy"}
