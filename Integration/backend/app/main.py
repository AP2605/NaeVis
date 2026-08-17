"""SIH-NAVIS Backend Application Entrypoint.

Backend service for GPS-denied autonomous drone navigation simulation,
providing telemetry ingestion, real-time streaming, and system integration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.telemetry import router as telemetry_router

app = FastAPI(
    title="SIH-NAVIS Backend",
    description="Backend service for the SIH-NAVIS GPS-denied autonomous drone navigation simulation system.",
    version="0.1.0",
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
        "version": "0.1.0",
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
