"""
Real-Time Telemetry & Simulation WebSocket Bridge Server (P3 Module).
=====================================================================
Central communication hub connecting Blender (P2), Navigation (P3), and Dashboard (P4):
  - Ingests high-rate `SensorPacket` stream from Blender (P2) on `/ws/sensors`.
  - Computes real-time 6-DOF state estimation and waypoint flight guidance.
  - Broadcasts `EstimatedPose` and `flight_command` to React 3D Dashboard (P4) on `/ws/telemetry`.
  - Compatible with all websockets library versions (including websockets 17.x).

Usage:
  python -m navigation.server.stream_server --host 0.0.0.0 --port 8765
"""

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Set, Dict, Any, Optional

# Ensure workspace root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from navigation.engine import NavigationEngine

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


class NavigationStreamServer:
    """
    Asynchronous WebSocket Streaming Server for Navis Navigation System.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765, waypoints_file: Optional[str] = None):
        self.host = host
        self.port = port
        self.engine = NavigationEngine()

        if waypoints_file and os.path.exists(waypoints_file):
            self.engine.load_waypoints(waypoints_file)
            print(f"[Server] Loaded mission waypoints from: {waypoints_file}")

        self.telemetry_clients: Set[Any] = set()
        self.sensor_clients: Set[Any] = set()
        self.frame_counter = 0

    async def register_telemetry_client(self, websocket):
        """Registers a P4 Dashboard client to receive live telemetry."""
        self.telemetry_clients.add(websocket)
        addr = getattr(websocket, "remote_address", "Client")
        print(f"[Server] P4 Dashboard connected: {addr} (Total clients: {len(self.telemetry_clients)})")
        try:
            await websocket.wait_closed()
        finally:
            self.telemetry_clients.discard(websocket)
            print(f"[Server] P4 Dashboard disconnected: {addr}")

    async def handle_sensor_feed(self, websocket):
        """Handles incoming sensor packets from P2 (Blender / Simulator)."""
        self.sensor_clients.add(websocket)
        addr = getattr(websocket, "remote_address", "Blender")
        print(f"[Server] P2 Blender connected: {addr}")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    self.frame_counter += 1

                    # Process sensor packet through P3 navigation engine
                    t0 = time.perf_counter()
                    output_packet = self.engine.process_packet(data)
                    dt_ms = (time.perf_counter() - t0) * 1000.0

                    # Send autonomous flight command back to Blender
                    flight_cmd = output_packet.get("flight_command", {})
                    response = {
                        "frame_id": output_packet["frame_id"],
                        "flight_command": flight_cmd,
                        "latency_ms": round(dt_ms, 2)
                    }
                    await websocket.send(json.dumps(response))

                    # Broadcast estimated pose to all connected P4 Dashboard clients
                    if self.telemetry_clients:
                        telemetry_json = json.dumps(output_packet)
                        await asyncio.gather(*[
                            client.send(telemetry_json)
                            for client in list(self.telemetry_clients)
                        ], return_exceptions=True)

                    if self.frame_counter % 15 == 0:
                        pose = output_packet["estimated_pose"]
                        cmd = flight_cmd
                        print(f"[Server] Frame #{self.frame_counter:04d} | Pos: ({pose['x']:.2f}, {pose['y']:.2f}, {pose['z']:.2f}) m | Latency: {dt_ms:.1f}ms | Target WP: {cmd.get('active_waypoint_idx')} ({cmd.get('active_waypoint_name')})")

                except Exception as e:
                    print(f"[Server] Error processing packet: {e}")

        finally:
            self.sensor_clients.discard(websocket)
            print(f"[Server] P2 Blender disconnected: {addr}")

    async def router(self, websocket, *args):
        """
        Universal WebSocket router supporting both websockets v14+ / v17+ (router(websocket))
        and legacy versions (router(websocket, path)).
        """
        path = "/"
        if hasattr(websocket, "request") and hasattr(websocket.request, "path"):
            path = websocket.request.path
        elif hasattr(websocket, "path"):
            path = websocket.path
        elif len(args) > 0 and isinstance(args[0], str):
            path = args[0]

        if "/sensors" in path:
            await self.handle_sensor_feed(websocket)
        else:
            await self.register_telemetry_client(websocket)

    async def start(self):
        """Starts the WebSocket server event loop on host:port."""
        if not WEBSOCKETS_AVAILABLE:
            print("\n[Server Error] 'websockets' library is not installed.")
            print("[Server Info] Please install it via: pip install websockets\n")
            return

        print("\n" + "=" * 65)
        print("    NAVIS NAVIGATION & TELEMETRY WEBSOCKET BRIDGE SERVER    ")
        print("=" * 65)
        print(f" Listening on: ws://{self.host}:{self.port}")
        print(f"  • P2 Blender Feed URL:     ws://{self.host}:{self.port}/ws/sensors")
        print(f"  • P4 Dashboard Stream URL: ws://{self.host}:{self.port}/ws/telemetry")
        print("=" * 65 + "\n")

        async with websockets.serve(self.router, self.host, self.port):
            await asyncio.Future()  # run forever


def main():
    parser = argparse.ArgumentParser(description="Navis Real-Time Telemetry Bridge Server.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port number (default: 8765)")
    parser.add_argument("--waypoints", type=str, default=None, help="Path to mission waypoints JSON")

    args = parser.parse_args()

    default_wp = os.path.join(root_dir, "navigation", "configs", "mission_waypoints.json")
    wp_path = args.waypoints if args.waypoints else (default_wp if os.path.exists(default_wp) else None)

    server = NavigationStreamServer(host=args.host, port=args.port, waypoints_file=wp_path)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Server] Shutdown signal received. Closing server.")


if __name__ == "__main__":
    main()
