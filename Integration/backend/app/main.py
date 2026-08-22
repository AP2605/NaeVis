"""SIH-NAVIS Backend Application Entrypoint.

Backend service for GPS-denied autonomous drone navigation simulation,
providing telemetry ingestion, real-time streaming, and system integration.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.integration import router as integration_router
from app.api.missions import router as missions_router
from app.api.p1 import router as p1_router
from app.api.p2 import router as p2_router
from app.api.p3 import router as p3_router
from app.api.telemetry import router as telemetry_router
from app.api.trajectory import router as trajectory_router
from app.config import settings
from app.websocket.camera import router as camera_websocket_router
from app.websocket.telemetry import router as telemetry_websocket_router

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sih_navis")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle and optional in-process P3 & P2 listeners."""
    nav_server_task = None
    nav_server_instance = None
    sim_server_task = None
    sim_server_instance = None

    # 1. Dedicated P3 Navigation Server (Port 8004)
    if settings.AUTO_START_NAV_SERVER:
        try:
            from app.websocket.navigation_server import create_nav_server_async
            nav_server_instance = await create_nav_server_async(
                host=settings.NAV_WS_HOST, port=settings.NAV_WS_PORT
            )
            nav_server_task = asyncio.create_task(nav_server_instance.serve())
            logger.info(
                "Started dedicated P3 Navigation WebSocket Server on ws://%s:%d%s",
                settings.NAV_WS_HOST,
                settings.NAV_WS_PORT,
                settings.NAV_WS_PATH,
            )
        except Exception as exc:
            logger.warning("Could not auto-start P3 Navigation Server on port %d: %s", settings.NAV_WS_PORT, exc)

    # 2. Dedicated P2 Simulation Ground Truth Server (Port 8005)
    if settings.AUTO_START_P2_SERVER:
        try:
            from app.websocket.simulation_server import create_sim_server_async
            sim_server_instance = await create_sim_server_async(
                host=settings.P2_WS_HOST, port=settings.P2_WS_PORT
            )
            sim_server_task = asyncio.create_task(sim_server_instance.serve())
            logger.info(
                "Started dedicated P2 Simulation Telemetry WebSocket Server on ws://%s:%d%s",
                settings.P2_WS_HOST,
                settings.P2_WS_PORT,
                settings.P2_WS_PATH,
            )
        except Exception as exc:
            logger.warning("Could not auto-start P2 Simulation Server on port %d: %s", settings.P2_WS_PORT, exc)

    yield

    # Graceful Shutdown
    if nav_server_instance is not None:
        nav_server_instance.should_exit = True
    if nav_server_task is not None:
        nav_server_task.cancel()
        try:
            await nav_server_task
        except (asyncio.CancelledError, Exception):
            pass

    if sim_server_instance is not None:
        sim_server_instance.should_exit = True
    if sim_server_task is not None:
        sim_server_task.cancel()
        try:
            await sim_server_task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST routers
app.include_router(health_router)
app.include_router(telemetry_router)
app.include_router(p1_router)
app.include_router(p2_router)
app.include_router(p3_router)
app.include_router(integration_router)
app.include_router(missions_router)
app.include_router(analytics_router)
app.include_router(trajectory_router)

# Register WebSocket routers
app.include_router(telemetry_websocket_router)
app.include_router(camera_websocket_router)


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
    "/dashboard",
    tags=["Dashboard"],
    summary="Integration Dashboard UI",
    include_in_schema=False,
)
def serve_dashboard():
    """Serve the integration web dashboard."""
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Dashboard template not found"}
