"""Dedicated P4 Navigation WebSocket Server for P3 SLAM / Navigation Ingestion.

Hosts dedicated listener on port 8004 (/ws/navigation) to receive real-time
6-DoF navigation estimation packets from P3 over LAN, forwarding validated payloads
into the central P4 ingestion pipeline (Frame Synchronizer, Trajectory DB, Telemetry Broadcaster).
"""

import argparse
import asyncio
import json
import logging
import time
from typing import Any
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.integrations.p3.service import p3_service

logger = logging.getLogger("sih_navis.websocket.navigation")

nav_app = FastAPI(
    title="SIH-NAVIS P3 Navigation WebSocket Listener",
    description="Dedicated port 8004 WebSocket listener for P3 navigation state ingestion",
    version="1.0.0",
)

# Enable CORS
nav_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@nav_app.get(
    "/health",
    tags=["Health"],
    summary="Navigation listener health check",
)
def nav_server_health():
    """Return health status of the dedicated navigation WebSocket listener."""
    return {
        "status": "online",
        "module": "P3 Navigation WebSocket Listener",
        "port": settings.NAV_WS_PORT,
        "endpoint": settings.NAV_WS_PATH,
    }


@nav_app.get(
    "/",
    tags=["Root"],
    summary="Root status",
)
def nav_server_root():
    """Root info for navigation listener."""
    return {
        "system": "SIH-NAVIS",
        "service": "P3 Navigation Receiver",
        "port": settings.NAV_WS_PORT,
        "endpoint": settings.NAV_WS_PATH,
    }


@nav_app.websocket("/ws/navigation")
async def websocket_navigation_endpoint(
    websocket: WebSocket,
    source: str = Query(
        default="auto",
        description="'real' for verified teammate stream, 'mock' for synthetic, 'auto' for config-based",
    ),
) -> None:
    """Dedicated WebSocket endpoint receiving real-time P3 navigation packets.

    Protocol:
    - Transport: Text WebSocket messages containing JSON.
    - Rate: Natural SLAM estimation output rate.
    - Ingestion: Validates and normalizes against NavigationStatePacket schema,
      updates Frame Synchronizer, Trajectory DB, and broadcasts live to dashboard.
    """
    await websocket.accept()
    client_host = getattr(websocket.client, "host", "unknown")
    client_port = getattr(websocket.client, "port", "unknown")
    logger.info("[P3 WS] Client connected from %s:%s on port %d", client_host, client_port, settings.NAV_WS_PORT)

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
                logger.warning("[P3 WS] Invalid JSON packet from %s: %s", client_host, json_err)
                try:
                    await websocket.send_json({
                        "status": "error",
                        "code": "INVALID_JSON",
                        "message": f"Malformed JSON payload: {str(json_err)}",
                    })
                except Exception:
                    pass
                continue

            # 2. Ingest through existing P3 service & normalization layer
            try:
                frame = await p3_service.process_navigation_packet(payload, is_real=is_real)
                packet_count += 1
                now = time.time()

                # Periodic rate-limited summary logging (every 50 packets or ~5 seconds)
                if (now - last_summary_time >= 5.0) or (packet_count % 50 == 0):
                    fid = frame.navigation.frame_id if frame.navigation else frame.frame_id
                    conf = frame.navigation.confidence if frame.navigation else 1.0
                    st = frame.navigation.tracking_state if frame.navigation else "OK"
                    src_tag = "REAL" if is_real else "MOCK"
                    logger.info(
                        "[P3 WS] Navigation stream active [%s]: frame=%d | state=%s | conf=%.2f | total=%d",
                        src_tag,
                        fid,
                        st,
                        conf,
                        packet_count,
                    )
                    last_summary_time = now

            except ValueError as val_err:
                invalid_packet_count += 1
                logger.warning("[P3 WS] Schema validation failed for packet from %s: %s", client_host, val_err)
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
                logger.warning("[P3 WS] Error ingesting navigation packet: %s", exc)
                continue

    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("[P3 WS] Client disconnected from %s:%s (total packets: %d)", client_host, client_port, packet_count)
    except Exception as exc:
        logger.warning("[P3 WS] Socket session exception for %s: %s", client_host, exc)


class SafeUvicornServer(uvicorn.Server):
    """Custom Uvicorn Server subclass that does not invoke sys.exit upon startup bind errors."""

    def install_signal_handlers(self) -> None:
        pass

    async def startup(self, sockets=None) -> None:
        try:
            await super().startup(sockets=sockets)
        except (Exception, SystemExit) as exc:
            self.should_exit = True
            logger.warning("[P3 WS] Background listener could not bind to %s:%s: %s", self.config.host, self.config.port, exc)


async def create_nav_server_async(host: str = settings.NAV_WS_HOST, port: int = settings.NAV_WS_PORT) -> uvicorn.Server:
    """Create and return configured Uvicorn Server instance for P3 navigation listener."""
    config = uvicorn.Config(
        app=nav_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    return SafeUvicornServer(config)


def main():
    """CLI entrypoint to run standalone P3 Navigation WebSocket Server."""
    parser = argparse.ArgumentParser(description="SIH-NAVIS Dedicated P3 Navigation WebSocket Server")
    parser.add_argument("--host", default=settings.NAV_WS_HOST, help="Host binding address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=settings.NAV_WS_PORT, help="Port number (default: 8004)")
    args = parser.parse_args()

    print("=" * 65)
    print("  SIH-NAVIS P3 Dedicated Navigation WebSocket Server")
    print("=" * 65)
    print(f"  Listening on: ws://{args.host}:{args.port}/ws/navigation")
    print(f"  Health probe: http://{args.host}:{args.port}/health")
    print("=" * 65)

    uvicorn.run(nav_app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
