"""WebSocket Camera Binary Streaming and Multi-Consumer Distribution Routers.

Endpoints:
- /ws/camera : Upstream producer feed and legacy camera viewer endpoint
- /ws/slam   : High-throughput binary camera consumer for visual SLAM
- /ws/video  : High-throughput binary camera consumer for Next.js frontend live optical stream
"""

import asyncio
import logging
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.services.camera_service import camera_service

logger = logging.getLogger("sih_navis.websocket.camera")

router = APIRouter(tags=["Camera WebSocket Streams"])


@router.websocket("/ws/camera")
async def websocket_camera(
    websocket: WebSocket,
    role: str = Query(
        default="viewer",
        description="'viewer' for dashboard displays, 'producer' for frame sources",
    ),
    source: str = Query(
        default="auto",
        description="'real' for verified teammate stream, 'mock' for synthetic, 'auto' for config-based",
    ),
) -> None:
    """WebSocket endpoint for camera frame streaming (backward compatible).

    - Producers push binary image frames (or structured binary packets).
    - Viewers receive image frames directly without JSON encoding overhead.
    """
    from app.config import settings
    is_real = (source.lower() == "real") or (settings.SOURCE_MODE.upper() == "REAL")

    if role.lower() == "producer":
        await camera_service.register_producer(websocket)
        try:
            while True:
                data = await websocket.receive_bytes()
                if data:
                    await camera_service.ingest_and_broadcast_frame(data, is_real=is_real)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.warning("[/ws/camera] Producer exception: %s", exc)
        finally:
            camera_service.unregister_producer(websocket)
    else:
        # Default: Viewer client
        await camera_service.register_viewer(websocket)
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    # Ingest if client pushes bytes
                    await camera_service.ingest_and_broadcast_frame(message["bytes"], is_real=is_real)
                elif "text" in message and message["text"]:
                    if message["text"] == "ping":
                        await websocket.send_text("pong")
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("[/ws/camera] Viewer terminated: %s", exc)
        finally:
            camera_service.unregister_viewer(websocket)


@router.websocket("/ws/slam")
async def websocket_slam(websocket: WebSocket) -> None:
    """WebSocket endpoint dedicated for Visual SLAM consumers.

    Streams binary packets formatted with 20-byte NAVC header [magic, frame_id, timestamp, payload_size, JPEG bytes].
    Allows SLAM teammates to extract frame metadata and correlate with P3 inertial estimates and telemetry.
    """
    await camera_service.register_slam_consumer(websocket)
    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                # If SLAM feedback/producer provides upstream frame
                await camera_service.ingest_and_broadcast_frame(message["bytes"])
            elif "text" in message and message["text"]:
                if message["text"] == "ping":
                    await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:
        logger.debug("[/ws/slam] SLAM client terminated: %s", exc)
    finally:
        camera_service.unregister_slam_consumer(websocket)


@router.websocket("/ws/video")
async def websocket_video(
    websocket: WebSocket,
    role: str = Query(
        default="viewer",
        description="'viewer' for frontend video display, 'producer' for frame sources",
    ),
    source: str = Query(
        default="auto",
        description="'real' for verified teammate stream, 'mock' for synthetic, 'auto' for config-based",
    ),
) -> None:
    """WebSocket endpoint dedicated for Frontend Live Video displays and Real P2 Camera Feed.

    - P2 Blender connects to ws://<P4-LAN-IP>:8000/ws/video and sends binary JPEG frames.
    - Frontend connects to ws://<P4-LAN-IP>:8000/ws/video (or /ws/camera) to receive live frames.
    - Supports both explicit role='producer' and implicit auto-promotion when binary frames are received.
    """
    from app.config import settings
    is_real = (source.lower() == "real") or (settings.SOURCE_MODE.upper() == "REAL")

    if role.lower() == "producer":
        await camera_service.register_producer(websocket)
        try:
            while True:
                data = await websocket.receive_bytes()
                if data:
                    await camera_service.ingest_and_broadcast_frame(data, is_real=is_real)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.warning("[/ws/video] Video producer exception: %s", exc)
        finally:
            camera_service.unregister_producer(websocket)
    else:
        # Default: Video consumer / viewer (auto-promotes to producer if incoming binary frames are pushed)
        await camera_service.register_video_consumer(websocket)
        is_promoted_producer = False
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    data = message["bytes"]
                    if not is_promoted_producer:
                        # Auto-promote to producer so socket only pushes upstream and receives no echo
                        camera_service.unregister_video_consumer(websocket)
                        await camera_service.register_producer(websocket)
                        is_promoted_producer = True
                    await camera_service.ingest_and_broadcast_frame(data, is_real=is_real)
                elif "text" in message and message["text"]:
                    if message["text"] == "ping":
                        await websocket.send_text("pong")
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("[/ws/video] Video socket terminated: %s", exc)
        finally:
            if is_promoted_producer:
                camera_service.unregister_producer(websocket)
            else:
                camera_service.unregister_video_consumer(websocket)

