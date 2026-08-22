"""WebSocket telemetry route handler supporting both Frontend Viewers and P2 Telemetry Producers."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.integrations.p2.service import p2_service
from app.schemas.websocket import TelemetryEvent, GroundTruthEvent, IntegratedStateEvent
from app.services.integration_service import integration_service
from app.websocket.manager import connection_manager

logger = logging.getLogger("sih_navis.websocket.telemetry")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/telemetry")
async def websocket_telemetry(
    websocket: WebSocket,
    role: str = Query(
        default="viewer",
        description="'viewer' for frontend dashboard display, 'producer' for P2 simulation telemetry sources",
    ),
    source: str = Query(
        default="auto",
        description="'real' for verified teammate stream, 'mock' for synthetic, 'auto' for config-based",
    ),
) -> None:
    """WebSocket endpoint for real-time telemetry streaming and P2 Ground Truth ingestion.

    - Viewers (Frontend Dashboard) receive 10 Hz broadcast of telemetry, integrated state,
      ground truth, navigation, analytics, and mission status.
    - Producers (P2 Blender / simulation) push ground-truth telemetry JSON packets.
    - Auto-promotes clients to producers if they stream ground-truth packets.
    """
    client_host = getattr(websocket.client, "host", "unknown")
    client_port = getattr(websocket.client, "port", "unknown")

    is_real = True
    if source.lower() == "mock":
        is_real = False
    elif source.lower() == "real":
        is_real = True
    elif settings.SOURCE_MODE.upper() == "MOCK":
        is_real = False

    is_producer = role.lower() == "producer"

    if is_producer:
        await websocket.accept()
        logger.info("[P2 TELEMETRY] Producer connected from %s:%s on /ws/telemetry", client_host, client_port)

        packet_count = 0
        last_summary_time = 0.0

        try:
            while True:
                data = await websocket.receive_text()
                if not data or not data.strip():
                    continue

                # 1. Parse JSON safely
                try:
                    payload = json.loads(data)
                except (json.JSONDecodeError, UnicodeDecodeError) as json_err:
                    logger.warning("[P2 TELEMETRY] Invalid JSON from %s: %s", client_host, json_err)
                    try:
                        await websocket.send_json({
                            "status": "error",
                            "code": "INVALID_JSON",
                            "message": f"Malformed JSON: {str(json_err)}",
                        })
                    except Exception:
                        pass
                    continue

                # Check ping
                if isinstance(payload, dict) and payload.get("type", "").lower() == "ping":
                    try:
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    except Exception:
                        pass
                    continue

                # 2. Ingest through P2 ground-truth pipeline
                try:
                    frame = await p2_service.process_ground_truth_packet(payload, is_real=is_real)
                    packet_count += 1
                    now = time.time()

                    # Periodic rate-limited summary logging (every 50 packets or ~5 seconds)
                    if (now - last_summary_time >= 5.0) or (packet_count % 50 == 0):
                        gt_pos = frame.ground_truth.position if frame.ground_truth else None
                        pos_str = f"({gt_pos.x:.1f}, {gt_pos.y:.1f}, {gt_pos.z:.1f})" if gt_pos else "(n/a)"
                        src_tag = "REAL" if is_real else "MOCK"
                        logger.info(
                            "[P2 TELEMETRY] Stream active [%s]: frame=%d | pos=%s | total=%d",
                            src_tag,
                            frame.frame_id,
                            pos_str,
                            packet_count,
                        )
                        last_summary_time = now

                except ValueError as val_err:
                    logger.warning("[P2 TELEMETRY] Schema validation failed for packet from %s: %s", client_host, val_err)
                    try:
                        await websocket.send_json({
                            "status": "error",
                            "code": "VALIDATION_FAILED",
                            "message": str(val_err),
                        })
                    except Exception:
                        pass
                    continue
                except Exception as exc:
                    logger.warning("[P2 TELEMETRY] Error ingesting ground truth from %s: %s", client_host, exc)
                    continue

        except (WebSocketDisconnect, asyncio.CancelledError):
            logger.info("[P2 TELEMETRY] Producer disconnected from %s:%s (total packets: %d)", client_host, client_port, packet_count)
        except Exception as exc:
            logger.warning("[P2 TELEMETRY] Producer socket error for %s: %s", client_host, exc)
        return

    # Default: Viewer Mode (Frontend Dashboard)
    await connection_manager.connect(websocket)
    logger.info("[Telemetry WS] Viewer connected from %s:%s.", client_host, client_port)

    # Send initial state snapshot immediately upon connection
    try:
        # 1. Telemetry
        initial_telemetry = integration_service.get_current_telemetry()
        await connection_manager.send_personal_json(TelemetryEvent(data=initial_telemetry), websocket)

        # 2. Integrated state (embeds latest ground_truth, navigation, perception, source_health)
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

        # 4. Active Mission if present
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
        logger.warning("[Telemetry WS] Error transmitting initial snapshot: %s", exc)

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
            logger.debug("[Telemetry WS] Stream task ended: %s", exc)

    async def message_receiver() -> None:
        """Handle incoming client messages (ping or ground-truth telemetry push)."""
        packet_count = 0
        last_summary_time = 0.0
        try:
            while True:
                data = await websocket.receive_text()
                if not data or not data.strip():
                    continue

                try:
                    payload = json.loads(data)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                if isinstance(payload, dict):
                    msg_type = payload.get("type", "").lower()
                    if msg_type == "ping":
                        await connection_manager.send_personal_json(
                            {
                                "type": "pong",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            websocket,
                        )
                        continue

                    # Auto-ingest if payload is P2 ground-truth telemetry
                    if "ground_truth" in payload or "position" in payload or "x" in payload:
                        try:
                            frame = await p2_service.process_ground_truth_packet(payload, is_real=is_real)
                            packet_count += 1
                            now = time.time()
                            if (now - last_summary_time >= 5.0) or (packet_count % 50 == 0):
                                gt_pos = frame.ground_truth.position if frame.ground_truth else None
                                pos_str = f"({gt_pos.x:.1f}, {gt_pos.y:.1f}, {gt_pos.z:.1f})" if gt_pos else "(n/a)"
                                src_tag = "REAL" if is_real else "MOCK"
                                logger.info(
                                    "[P2 TELEMETRY] Ingested from viewer socket [%s]: frame=%d | pos=%s | total=%d",
                                    src_tag,
                                    frame.frame_id,
                                    pos_str,
                                    packet_count,
                                )
                                last_summary_time = now
                        except Exception as exc:
                            logger.debug("[P2 TELEMETRY] Ingestion failed: %s", exc)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("[Telemetry WS] Receive loop terminated: %s", exc)

    streamer_task = asyncio.create_task(telemetry_streamer())
    receiver_task = asyncio.create_task(message_receiver())

    try:
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
        logger.debug("[Telemetry WS] Session terminated: %s", exc)
    finally:
        connection_manager.disconnect(websocket)
        logger.info("[Telemetry WS] Viewer disconnected: %s:%s", client_host, client_port)
