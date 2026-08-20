"""WebSocket Camera binary streaming router."""

import asyncio
import logging
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.services.camera_service import camera_service

logger = logging.getLogger("sih_navis.websocket.camera")

router = APIRouter(tags=["Camera WebSocket"])


@router.websocket("/ws/camera")
async def websocket_camera(
    websocket: WebSocket,
    role: str = Query(default="viewer", description="'viewer' for dashboard displays, 'producer' for frame sources"),
) -> None:
    """WebSocket endpoint for high-frequency binary camera frame streaming.

    Transfers raw JPEG/PNG image frames independently from JSON telemetry.
    Supports both frame producers (simulation/mock) and multiple dashboard viewers.
    """
    if role.lower() == "producer":
        await camera_service.register_producer(websocket)
        try:
            while True:
                # Producers send binary image frames
                data = await websocket.receive_bytes()
                if data:
                    await camera_service.ingest_and_broadcast_frame(data)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.warning("Camera producer socket exception: %s", exc)
        finally:
            camera_service.unregister_producer(websocket)
    else:
        # Default: Viewer client (frontend dashboard)
        await camera_service.register_viewer(websocket)
        try:
            while True:
                # Keep connection alive, listen for messages or auto-detect if producer sends bytes
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    # Viewer unexpectedly pushed a frame, auto-forward
                    await camera_service.ingest_and_broadcast_frame(message["bytes"])
                elif "text" in message and message["text"]:
                    if message["text"] == "ping":
                        await websocket.send_text("pong")
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("Camera viewer socket terminated: %s", exc)
        finally:
            camera_service.unregister_viewer(websocket)
