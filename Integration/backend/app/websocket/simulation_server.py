"""Dedicated P4 Simulation Ground Truth WebSocket Server for P2 Ingestion.

Hosts dedicated listener on port 8005 (/ws/telemetry) to receive real-time
6-DoF simulation ground-truth packets from P2 (Blender) over LAN, completely isolated from
the P2 video/camera stream on port 8000.
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.integrations.p2.service import p2_service

logger = logging.getLogger("sih_navis.websocket.simulation")

sim_app = FastAPI(
    title="SIH-NAVIS P2 Simulation Telemetry WebSocket Listener",
    description="Dedicated port 8005 WebSocket listener for P2 ground-truth telemetry ingestion",
    version="1.0.0",
)

# Enable CORS
sim_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@sim_app.get(
    "/health",
    tags=["Health"],
    summary="Simulation telemetry listener health check",
)
def sim_server_health():
    """Return health status of the dedicated P2 simulation WebSocket listener."""
    return {
        "status": "online",
        "module": "P2 Simulation Ground Truth WebSocket Listener",
        "port": settings.P2_WS_PORT,
        "endpoint": settings.P2_WS_PATH,
    }


@sim_app.get(
    "/",
    tags=["Root"],
    summary="Root status",
)
def sim_server_root():
    """Root info for P2 simulation listener."""
    return {
        "system": "SIH-NAVIS",
        "service": "P2 Simulation Ground Truth Receiver",
        "port": settings.P2_WS_PORT,
        "endpoint": settings.P2_WS_PATH,
    }


@sim_app.websocket("/ws/telemetry")
@sim_app.websocket("/ws/ground-truth")
async def websocket_simulation_telemetry(
    websocket: WebSocket,
    source: str = Query(
        default="auto",
        description="'real' for verified teammate stream, 'mock' for synthetic, 'auto' for config-based",
    ),
) -> None:
    """Dedicated WebSocket endpoint receiving real-time P2 ground-truth telemetry packets on port 8005.

    Protocol:
    - Transport: Text WebSocket messages containing JSON.
    - Rate: Natural simulation physics/output rate.
    - Ingestion: Validates and normalizes against SimulationGroundTruthPacket schema,
      updates Frame Synchronizer, Ground Truth Trajectory DB, and broadcasts live to dashboard.
    """
    await websocket.accept()
    client_host = getattr(websocket.client, "host", "unknown")
    client_port = getattr(websocket.client, "port", "unknown")
    logger.info("[P2 TELEMETRY] Client connected from %s:%s on port %d", client_host, client_port, settings.P2_WS_PORT)

    # Determine real vs mock provenance
    is_real = True
    if source.lower() == "mock":
        is_real = False
    elif source.lower() == "real":
        is_real = True
    elif settings.SOURCE_MODE.upper() == "MOCK":
        is_real = False

    last_summary_time = 0.0
    packet_count = 0
    invalid_packet_count = 0

    try:
        while True:
            message = await websocket.receive_text()
            if not message or not message.strip():
                continue

            # 1. Parse JSON safely
            try:
                payload = json.loads(message)
            except (json.JSONDecodeError, UnicodeDecodeError) as json_err:
                invalid_packet_count += 1
                logger.warning("[P2 TELEMETRY] Invalid JSON packet from %s: %s", client_host, json_err)
                try:
                    await websocket.send_json({
                        "status": "error",
                        "code": "INVALID_JSON",
                        "message": f"Malformed JSON payload: {str(json_err)}",
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

            # 2. Ingest through existing P2 service & normalization layer
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
                invalid_packet_count += 1
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
                invalid_packet_count += 1
                logger.warning("[P2 TELEMETRY] Error ingesting ground truth packet from %s: %s", client_host, exc)
                continue

    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("[P2 TELEMETRY] Client disconnected from %s:%s (total packets: %d)", client_host, client_port, packet_count)
    except Exception as exc:
        logger.warning("[P2 TELEMETRY] Socket session error for %s: %s", client_host, exc)


class SafeUvicornServer(uvicorn.Server):
    """Custom Uvicorn Server subclass that does not invoke sys.exit upon startup bind errors."""

    def install_signal_handlers(self) -> None:
        pass

    async def startup(self, sockets=None) -> None:
        try:
            await super().startup(sockets=sockets)
        except (Exception, SystemExit) as exc:
            self.should_exit = True
            logger.warning("[P2 TELEMETRY] Background listener could not bind to %s:%s: %s", self.config.host, self.config.port, exc)


async def create_sim_server_async(host: str = settings.P2_WS_HOST, port: int = settings.P2_WS_PORT) -> uvicorn.Server:
    """Create and return configured Uvicorn Server instance for P2 simulation telemetry listener."""
    config = uvicorn.Config(
        app=sim_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    return SafeUvicornServer(config)


def main():
    """CLI entrypoint to run standalone P2 Simulation Telemetry WebSocket Server on port 8005."""
    parser = argparse.ArgumentParser(description="SIH-NAVIS Dedicated P2 Simulation Ground Truth WebSocket Server")
    parser.add_argument("--host", default=settings.P2_WS_HOST, help="Host binding address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=settings.P2_WS_PORT, help="Port number (default: 8005)")
    args = parser.parse_args()

    print("=" * 65)
    print("  SIH-NAVIS P2 Dedicated Simulation Telemetry WebSocket Server")
    print("=" * 65)
    print(f"  Listening on: ws://{args.host}:{args.port}/ws/telemetry")
    print(f"  Health probe: http://{args.host}:{args.port}/health")
    print("=" * 65)

    uvicorn.run(sim_app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
