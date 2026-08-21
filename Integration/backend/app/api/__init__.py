"""API routes module."""

from app.api.health import router as health_router
from app.api.integration import router as integration_router
from app.api.p1 import router as p1_router
from app.api.p2 import router as p2_router
from app.api.p3 import router as p3_router
from app.api.telemetry import router as telemetry_router

__all__ = [
    "health_router",
    "telemetry_router",
    "p1_router",
    "p2_router",
    "p3_router",
    "integration_router",
]
