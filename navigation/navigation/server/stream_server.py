"""
Real-Time Telemetry & Simulation WebSocket Bridge Server (P3 Module).
=====================================================================
Central communication hub connecting Blender (P2), Navigation (P3), and Dashboard (P4):
  - Ingests high-rate `SensorPacket` stream from Blender (P2) on `/ws/sensors`.
  - Ingests optional binary JPEG video stream on `/ws/video`.
  - Computes real-time 6-DOF state estimation and waypoint flight guidance.
  - Broadcasts `EstimatedPose` and `flight_command` to React 3D Dashboard (P4) on `/ws/telemetry`.
  - Optional Live HUD Cockpit Video Window (--view).

Usage:
  python -m navigation.server.stream_server --host 0.0.0.0 --port 8765
  python -m navigation.server.stream_server --view
"""

import argparse
import asyncio
import json
import os
import sys
import time
import cv2
import numpy as np
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
    Asynchronous WebSocket & Telemetry Streaming Server for Navis Navigation System.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        waypoints_file: Optional[str] = None,
        enable_view: bool = False
    ):
        self.host = host
        self.port = port
        self.enable_view = enable_view
        self.engine = NavigationEngine()

        if waypoints_file and os.path.exists(waypoints_file):
            self.engine.load_waypoints(waypoints_file)
            print(f"[Server] Loaded mission waypoints from: {waypoints_file}")

        self.telemetry_clients: Set[Any] = set()
        self.sensor_clients: Set[Any] = set()
        self.video_clients: Set[Any] = set()
        self.frame_counter = 0
        self.latest_video_frame: Optional[np.ndarray] = None
        self.latest_output_packet: Dict[str, Any] = {}

    def draw_hud(self, frame: Optional[np.ndarray], output_packet: Dict[str, Any]) -> np.ndarray:
        """Renders an aerospace-grade tactical HUD overlay on the drone's camera frame."""
        pose = output_packet.get("estimated_pose", {})
        flight_cmd = output_packet.get("flight_command", {})
        fid = output_packet.get("frame_id", self.frame_counter)
        state = output_packet.get("tracking_state", "STANDBY")
        conf = output_packet.get("confidence", 1.0) * 100.0

        if frame is not None:
            vis = cv2.resize(frame, (800, 450)) if (frame.shape[1] != 800 or frame.shape[0] != 450) else frame.copy()
        else:
            # Create synthetic tactical radar/HUD display
            vis = np.zeros((450, 800, 3), dtype=np.uint8)
            vis[:] = (18, 22, 28)  # Dark slate background

            # Draw background grid
            for gx in range(0, 800, 50):
                cv2.line(vis, (gx, 0), (gx, 450), (25, 32, 40), 1)
            for gy in range(0, 450, 50):
                cv2.line(vis, (0, gy), (800, gy), (25, 32, 40), 1)

        h, w = vis.shape[:2]
        cx, cy = w // 2, h // 2
        color_green = (0, 255, 120)
        color_cyan = (255, 230, 0)
        color_white = (255, 255, 255)

        # 1. Central Crosshair
        cv2.line(vis, (cx - 25, cy), (cx + 25, cy), color_green, 1)
        cv2.line(vis, (cx, cy - 25), (cx, cy + 25), color_green, 1)
        cv2.circle(vis, (cx, cy), 12, color_green, 1)

        # 2. Semi-transparent top & bottom telemetry banners
        overlay = vis.copy()
        cv2.rectangle(overlay, (0, 0), (w, 38), (10, 14, 20), -1)
        cv2.rectangle(overlay, (0, h - 50), (w, h), (10, 14, 20), -1)
        vis = cv2.addWeighted(overlay, 0.75, vis, 0.25, 0)

        # 3. Top Banner
        cv2.putText(vis, f"NAVIS GPS-DENIED AUTONOMOUS VIO | FRAME: #{fid:05d}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color_cyan, 1, cv2.LINE_AA)
        cv2.putText(vis, f"STATE: {state} ({conf:.0f}%)", (w - 260, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color_green, 1, cv2.LINE_AA)

        # 4. Bottom Banner
        x = pose.get("x", 0.0)
        y = pose.get("y", 0.0)
        z = pose.get("z", 0.0)
        yaw = pose.get("yaw", 0.0)
        wp_idx = flight_cmd.get("active_waypoint_idx", "-")
        wp_name = flight_cmd.get("active_waypoint_name", "Navigating")
        dist = flight_cmd.get("distance_to_waypoint_m", 0.0)
        speed = flight_cmd.get("desired_velocity_mps", 0.0)

        cv2.putText(vis, f"POS: X:{x:+.1f}m  Y:{y:+.1f}m  ALT:{z:.1f}m | HDG:{yaw:+.0f}deg | SPD:{speed:.1f}m/s", (15, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color_white, 1, cv2.LINE_AA)
        cv2.putText(vis, f"ACTIVE WAYPOINT: #{wp_idx} ({wp_name}) | DISTANCE REMAINING: {dist:.1f}m", (15, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_green, 1, cv2.LINE_AA)

        return vis

    def render_live_view(self, frame: Optional[np.ndarray], output_packet: Dict[str, Any]):
        """Displays the tactical cockpit HUD window."""
        if not self.enable_view:
            return
        try:
            display_frame = frame if frame is not None else self.latest_video_frame
            hud_frame = self.draw_hud(display_frame, output_packet)
            cv2.imshow("NAVIS DRONE POV — LIVE COCKPIT FEED", hud_frame)
            cv2.waitKey(1)
        except Exception:
            pass

    async def register_telemetry_client(self, websocket):
        """Registers a P4 Dashboard client to receive live telemetry."""
        self.telemetry_clients.add(websocket)
        addr = getattr(websocket, "remote_address", "Client")
        print(f"[Server] P4 Dashboard connected: {addr} (Active clients: {len(self.telemetry_clients)})")
        try:
            await websocket.wait_closed()
        finally:
            self.telemetry_clients.discard(websocket)
            print(f"[Server] P4 Dashboard disconnected: {addr}")

    async def handle_video_feed(self, websocket):
        """Handles incoming binary JPEG video stream from Blender on /ws/video."""
        self.video_clients.add(websocket)
        addr = getattr(websocket, "remote_address", "Blender Video")
        print(f"[Server] P2 Blender Video Stream connected: {addr}")
        try:
            async for message in websocket:
                try:
                    if isinstance(message, bytes):
                        nparr = np.frombuffer(message, np.uint8)
                        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if decoded is not None:
                            self.latest_video_frame = decoded
                            if self.enable_view and self.latest_output_packet:
                                self.render_live_view(self.latest_video_frame, self.latest_output_packet)
                except Exception:
                    pass
        finally:
            self.video_clients.discard(websocket)
            print(f"[Server] P2 Blender Video Stream disconnected: {addr}")

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
                    self.latest_output_packet = output_packet

                    # Optional Live Cockpit Window
                    if self.enable_view:
                        frame_img = self.engine._load_camera_frame(data.get("camera", {}))
                        self.render_live_view(frame_img, output_packet)

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
        """Universal WebSocket router supporting websockets 17.x and legacy versions."""
        path = "/"
        if hasattr(websocket, "request") and hasattr(websocket.request, "path"):
            path = websocket.request.path
        elif hasattr(websocket, "path"):
            path = websocket.path
        elif len(args) > 0 and isinstance(args[0], str):
            path = args[0]

        if "/sensors" in path:
            await self.handle_sensor_feed(websocket)
        elif "/video" in path:
            await self.handle_video_feed(websocket)
        else:
            await self.register_telemetry_client(websocket)

    async def start(self):
        """Starts the WebSocket server event loop."""
        if not WEBSOCKETS_AVAILABLE:
            print("\n[Server Error] 'websockets' library is not installed.")
            print("[Server Info] Please install it via: pip install websockets\n")
            return

        print("\n" + "=" * 65)
        print("    NAVIS NAVIGATION & TELEMETRY WEBSOCKET BRIDGE SERVER    ")
        print("=" * 65)
        print(f" Listening on: ws://{self.host}:{self.port}")
        print(f"  • P2 Blender Sensor Feed:  ws://{self.host}:{self.port}/ws/sensors")
        print(f"  • P2 Blender Video Stream: ws://{self.host}:{self.port}/ws/video")
        print(f"  • P4 Dashboard Stream:     ws://{self.host}:{self.port}/ws/telemetry")
        if self.enable_view:
            print(f"  • Live Cockpit HUD Window: ENABLED")
        print("=" * 65 + "\n")

        async with websockets.serve(self.router, self.host, self.port):
            await asyncio.Future()  # run forever


def main():
    parser = argparse.ArgumentParser(description="Navis Real-Time Telemetry Bridge Server.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port number (default: 8765)")
    parser.add_argument("--waypoints", type=str, default=None, help="Path to mission waypoints JSON")
    parser.add_argument("--view", action="store_true", help="Enable Live Cockpit HUD Video Window")

    args = parser.parse_args()

    default_wp = os.path.join(root_dir, "navigation", "configs", "mission_waypoints.json")
    wp_path = args.waypoints if args.waypoints else (default_wp if os.path.exists(default_wp) else None)

    server = NavigationStreamServer(
        host=args.host,
        port=args.port,
        waypoints_file=wp_path,
        enable_view=args.view
    )
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Server] Shutdown signal received. Closing server.")
        if args.view:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
