"""WebSocket telemetry route handler."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.schemas.websocket import TelemetryEvent
from app.services.telemetry_service import telemetry_service
from app.websocket.manager import connection_manager

logger = logging.getLogger("sih_navis.websocket")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time telemetry streaming.

    Streams telemetry events to connected clients at the configured
    TELEMETRY_STREAM_INTERVAL rate.
    """
    await connection_manager.connect(websocket)
    logger.info("Telemetry stream started for client.")

    async def telemetry_streamer() -> None:
        """Stream telemetry events continuously at the configured interval."""
        try:
            while True:
                telemetry = telemetry_service.get_current_telemetry()
                event = TelemetryEvent(data=telemetry)
                sent = await connection_manager.send_personal_json(event, websocket)
                if not sent:
                    break
                await asyncio.sleep(settings.TELEMETRY_STREAM_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Telemetry stream task error: %s", exc)

    async def message_receiver() -> None:
        """Handle incoming client messages (e.g. ping)."""
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    msg_type = msg.get("type", "").lower()
                    if msg_type == "ping":
                        await connection_manager.send_personal_json(
                            {
                                "type": "pong",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            websocket,
                        )
                    else:
                        logger.info("Received client message of type: %s", msg_type)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received from WebSocket client: %s", data[:50])
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.warning("WebSocket receive loop error: %s", exc)

    streamer_task = asyncio.create_task(telemetry_streamer())
    receiver_task = asyncio.create_task(message_receiver())

    try:
        # Wait until either the stream task or receive task terminates
        done, pending = await asyncio.wait(
            [streamer_task, receiver_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except Exception as exc:
        logger.warning("WebSocket session error: %s", exc)
    finally:
        connection_manager.disconnect(websocket)
        logger.info("Telemetry stream stopped for client.")
