"""SIH-NAVIS Backend Application Entrypoint.

Backend service for GPS-denied autonomous drone navigation simulation,
providing telemetry ingestion, real-time streaming, and system integration.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.telemetry import router as telemetry_router
from app.config import settings
from app.websocket.telemetry import router as websocket_router

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sih_navis")

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(telemetry_router)
app.include_router(websocket_router)


@app.get(
    "/",
    tags=["Root"],
    summary="Root system status",
)
def read_root():
    """Root endpoint returning system info and status."""
    return {
        "system": "SIH-NAVIS",
        "status": "online",
        "version": settings.APP_VERSION,
    }


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
)
def read_health():
    """Health check endpoint to verify backend service liveness."""
    return {
        "status": "healthy",
    }
