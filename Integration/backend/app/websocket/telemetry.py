"""WebSocket telemetry route handler."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.schemas.websocket import TelemetryEvent
from app.services.integration_service import integration_service
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

    # Send initial state snapshot immediately upon connection
    try:
        # 1. Telemetry
        initial_telemetry = integration_service.get_current_telemetry()
        await connection_manager.send_personal_json(TelemetryEvent(data=initial_telemetry), websocket)

        # 2. Integrated state (embeds latest ground_truth, navigation, and perception)
        from app.schemas.websocket import IntegratedStateEvent
        initial_state = integration_service.get_current_integrated_state()
        await connection_manager.send_personal_json(IntegratedStateEvent(data=initial_state), websocket)

        # 3. Analytics
        from app.services.analytics_service import analytics_service
        metrics = analytics_service.compute_metrics()
        await connection_manager.send_personal_json({
            "event": "analytics",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": metrics.model_dump(),
        }, websocket)

        # 6. Active Mission if present
        from app.services.mission_service import mission_service
        active_m = mission_service.get_active_mission()
        if active_m is not None:
            await connection_manager.send_personal_json({
                "event": "mission_status",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "mission_id": active_m.mission_id,
                    "status": active_m.status.value,
                    "action": "mission_sync",
                    "mission": active_m.model_dump(),
                },
            }, websocket)
    except Exception as exc:
        logger.warning("Error transmitting initial WebSocket snapshot: %s", exc)

    async def telemetry_streamer() -> None:
        """Stream telemetry events continuously at the configured interval."""
        try:
            while True:
                telemetry = integration_service.get_current_telemetry()
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
