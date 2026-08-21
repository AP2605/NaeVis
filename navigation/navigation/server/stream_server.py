"""
Real-Time Telemetry & Simulation Dual Bridge Server (P3 Module).
===============================================================
Central communication hub connecting Blender (P2), Navigation (P3), and Dashboard (P4):
  - Ingests SensorPacket stream from Blender (P2) via HTTP POST (/api/packet) or WebSockets (/ws/sensors).
  - Computes real-time 6-DOF state estimation and waypoint flight guidance.
  - Broadcasts EstimatedPose and flight_command to React 3D Dashboard (P4) on /ws/telemetry.
  - Zero-dependency client support: Blender can use built-in urllib without installing any extra packages!

Usage:
  python -m navigation.server.stream_server --port 8765
"""

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Set, Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

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
    Dual HTTP REST & WebSocket Streaming Server for Navis Navigation System.
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
        self.lock = threading.Lock()
        self._loop = None

    def process_incoming_sensor_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Processes incoming frame synchronously thread-safe."""
        with self.lock:
            self.frame_counter += 1
            t0 = time.perf_counter()
            output_packet = self.engine.process_packet(data)
            dt_ms = (time.perf_counter() - t0) * 1000.0

            flight_cmd = output_packet.get("flight_command", {})
            response = {
                "frame_id": output_packet["frame_id"],
                "flight_command": flight_cmd,
                "latency_ms": round(dt_ms, 2)
            }

            if self.frame_counter % 15 == 0:
                pose = output_packet["estimated_pose"]
                cmd = flight_cmd
                print(f"[Server] Frame #{self.frame_counter:04d} | Pos: ({pose['x']:.2f}, {pose['y']:.2f}, {pose['z']:.2f}) m | Latency: {dt_ms:.1f}ms | Target WP: {cmd.get('active_waypoint_idx')} ({cmd.get('active_waypoint_name')})")

            # Broadcast to connected P4 WebSockets
            if self._loop and self.telemetry_clients:
                telemetry_json = json.dumps(output_packet)
                asyncio.run_coroutine_threadsafe(self._broadcast_telemetry(telemetry_json), self._loop)

            return response

    async def _broadcast_telemetry(self, telemetry_json: str):
        """Asynchronously broadcast telemetry to all P4 clients."""
        if self.telemetry_clients:
            await asyncio.gather(*[
                client.send(telemetry_json)
                for client in list(self.telemetry_clients)
            ], return_exceptions=True)

    async def register_telemetry_client(self, websocket):
        """Registers a P4 Dashboard client to receive live telemetry."""
        self.telemetry_clients.add(websocket)
        print(f"[Server] P4 Dashboard connected: {websocket.remote_address} (Active clients: {len(self.telemetry_clients)})")
        try:
            await websocket.wait_closed()
        finally:
            self.telemetry_clients.discard(websocket)
            print(f"[Server] P4 Dashboard disconnected: {websocket.remote_address}")

    async def handle_sensor_feed(self, websocket):
        """Handles incoming sensor packets from P2 via WebSockets."""
        self.sensor_clients.add(websocket)
        print(f"[Server] P2 Blender connected via WebSocket: {websocket.remote_address}")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    resp = self.process_incoming_sensor_data(data)
                    await websocket.send(json.dumps(resp))
                except Exception as e:
                    print(f"[Server] Error processing WebSocket packet: {e}")
        finally:
            self.sensor_clients.discard(websocket)
            print(f"[Server] P2 Blender disconnected: {websocket.remote_address}")

    async def ws_handler(self, websocket, *args):
        """Universal WebSocket handler compatible with all websockets library versions."""
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

    def start_http_server(self):
        """Starts a background HTTP REST server for zero-dependency Blender POST requests."""
        server_instance = self

        class NavisHTTPHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                if self.path == "/health" or self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "healthy", "service": "Navis P3 Navigation"}).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/api/packet" or self.path == "/api/sensors":
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length)
                    try:
                        data = json.loads(post_data.decode('utf-8'))
                        resp = server_instance.process_incoming_sensor_data(data)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps(resp).encode("utf-8"))
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

        httpd = HTTPServer((self.host, self.port), NavisHTTPHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"[Server] HTTP REST API live on: http://{self.host}:{self.port}/api/packet")

    async def start(self):
        """Starts both HTTP REST and WebSocket servers concurrently."""
        self._loop = asyncio.get_running_loop()
        self.start_http_server()

        if WEBSOCKETS_AVAILABLE:
            print("\n" + "=" * 65)
            print("    NAVIS NAVIGATION & TELEMETRY LIVE BRIDGE SERVER    ")
            print("=" * 65)
            print(f" Listening on: {self.host}:{self.port}")
            print(f"  • P2 Blender HTTP URL:    http://{self.host}:{self.port}/api/packet")
            print(f"  • P2 Blender WS URL:      ws://{self.host}:{self.port}/ws/sensors")
            print(f"  • P4 Dashboard WS URL:    ws://{self.host}:{self.port}/ws/telemetry")
            print("=" * 65 + "\n")

            try:
                ws_port = self.port + 1
                print(f"[Server] WebSocket server running on: ws://{self.host}:{ws_port}")
                async with websockets.serve(self.ws_handler, self.host, ws_port):
                    await asyncio.Future()
            except Exception as e:
                print(f"[Server Notice] Running in high-performance HTTP mode ({e})")
                while True:
                    await asyncio.sleep(3600)
        else:
            print("[Server Notice] Running in HTTP REST mode (zero-dependency).")
            while True:
                await asyncio.sleep(3600)


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
