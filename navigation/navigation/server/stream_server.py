"""
Real-Time Telemetry & Simulation WebSocket Bridge Server (P3 Module).
=====================================================================
Central communication hub connecting Blender (P2), Navigation (P3), and Dashboard (P4):
  - Ingests high-rate `SensorPacket` stream from Blender (P2) on `/ws/sensors`.
  - Computes real-time 6-DOF state estimation, VIO, and waypoint flight guidance (The Pilot).
  - Returns autonomous flight steering commands to Blender (P2).
  - Automatically streams real-time navigation telemetry to P4 on:
      ws://10.110.7.40:8004/ws/navigation
  - Consumes optional synchronized binary camera frames from P4 on:
      ws://10.110.7.40:8000/ws/slam (20-byte NAVC header)
  - Broadcasts `EstimatedPose` on local `/ws/telemetry`.
  - Optional Live Cockpit HUD Video Window (--view).
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time
import struct
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
        p4_ip: str = "10.110.7.40",
        p4_port: int = 8004,
        p4_video_port: int = 8000,
        waypoints_file: Optional[str] = None,
        enable_view: bool = False,
        enable_mock: bool = False
    ):
        self.host = host
        self.port = port
        self.p4_ip = p4_ip
        self.p4_port = p4_port
        self.p4_video_port = p4_video_port
        self.p4_ws_url = f"ws://{p4_ip}:{p4_port}/ws/navigation"
        self.enable_view = enable_view
        self.enable_mock = enable_mock
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

        # Queue for non-blocking P4 WebSocket stream
        self.p4_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        self.p4_connected = False

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
            vis = np.zeros((450, 800, 3), dtype=np.uint8)
            vis[:] = (18, 22, 28)
            for gx in range(0, 800, 50):
                cv2.line(vis, (gx, 0), (gx, 450), (25, 32, 40), 1)
            for gy in range(0, 450, 50):
                cv2.line(vis, (0, gy), (800, gy), (25, 32, 40), 1)

        h, w = vis.shape[:2]
        cx, cy = w // 2, h // 2
        color_green = (0, 255, 120)
        color_cyan = (255, 230, 0)
        color_white = (255, 255, 255)

        cv2.line(vis, (cx - 25, cy), (cx + 25, cy), color_green, 1)
        cv2.line(vis, (cx, cy - 25), (cx, cy + 25), color_green, 1)
        cv2.circle(vis, (cx, cy), 12, color_green, 1)

        overlay = vis.copy()
        cv2.rectangle(overlay, (0, 0), (w, 38), (10, 14, 20), -1)
        cv2.rectangle(overlay, (0, h - 50), (w, h), (10, 14, 20), -1)
        vis = cv2.addWeighted(overlay, 0.75, vis, 0.25, 0)

        p4_stat = "P4: ONLINE" if self.p4_connected else "P4: CONNECTING"
        mode_str = "[MISSION MOCK]" if self.enable_mock else "[LIVE BLENDER]"
        cv2.putText(vis, f"NAVIS AUTONOMOUS GUIDANCE PILOT {mode_str} | FRAME: #{fid:05d} | {p4_stat}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color_cyan, 1, cv2.LINE_AA)
        cv2.putText(vis, f"STATE: {state} ({conf:.0f}%)", (w - 260, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.50, color_green, 1, cv2.LINE_AA)

        x = pose.get("x", 0.0)
        y = pose.get("y", 0.0)
        z = pose.get("z", 0.0)
        roll = pose.get("roll", 0.0)
        pitch = pose.get("pitch", 0.0)
        yaw = pose.get("yaw", 0.0)
        wp_idx = flight_cmd.get("active_waypoint_idx", "-")
        wp_name = flight_cmd.get("active_waypoint_name", "Navigating")
        dist = flight_cmd.get("distance_to_waypoint_m", 0.0)
        speed = flight_cmd.get("desired_velocity_mps", 0.0)

        cv2.putText(vis, f"POS: X:{x:+.1f}m  Y:{y:+.1f}m  ALT:{z:.1f}m | ATT: R:{roll:+.0f}° P:{pitch:+.0f}° Y:{yaw:+.0f}° | SPD:{speed:.1f}m/s", (15, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_white, 1, cv2.LINE_AA)
        cv2.putText(vis, f"MISSION WP: #{wp_idx} ({wp_name}) | DISTANCE: {dist:.1f}m", (15, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_green, 1, cv2.LINE_AA)

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

    async def p4_forwarder_loop(self):
        """
        Background task connecting P3 to P4's WebSocket at ws://<P4-IP>:8004/ws/navigation
        Streams exact Navigation State packets continuously at natural SLAM rate.
        """
        print(f"[P3 -> P4 Forwarder] Initializing connection to: {self.p4_ws_url}")
        while True:
            try:
                async with websockets.connect(self.p4_ws_url, ping_interval=5, ping_timeout=5) as p4_ws:
                    self.p4_connected = True
                    print(f"\n[P3 -> P4 SUCCESS] Connected to P4 Navigation WebSocket: {self.p4_ws_url}\n")
                    while True:
                        payload = await self.p4_queue.get()
                        try:
                            await p4_ws.send(payload)
                        except Exception:
                            break
            except Exception:
                self.p4_connected = False
                await asyncio.sleep(2.0)

    async def p4_camera_consumer_loop(self):
        """
        Optional background task connecting to P4's binary camera stream at ws://<P4-IP>:8000/ws/slam
        Decodes 20-byte NAVC header and passes synchronized frames into the SLAM pipeline.
        """
        header_format = ">4sIdI"
        header_size = 20
        p4_cam_url = f"ws://{self.p4_ip}:{self.p4_video_port}/ws/slam"

        while True:
            try:
                async with websockets.connect(p4_cam_url, ping_interval=5, ping_timeout=5, max_size=10_000_000) as ws:
                    print(f"[P4 -> P3 CAMERA] Connected to P4 SLAM binary stream: {p4_cam_url}")
                    async for message in ws:
                        if isinstance(message, bytes) and len(message) >= header_size:
                            magic, frame_id, timestamp, payload_size = struct.unpack(header_format, message[:header_size])
                            if magic == b"NAVC":
                                jpeg_bytes = message[header_size:header_size + payload_size]
                                np_arr = np.frombuffer(jpeg_bytes, np.uint8)
                                decoded = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                                if decoded is not None:
                                    self.latest_video_frame = decoded
            except Exception:
                await asyncio.sleep(3.0)

    async def mock_simulation_loop(self):
        """
        Generates realistic synthetic 3D mission waypoint flight and streams to P4 + Cockpit HUD.
        Executes waypoints: Takeoff -> Forest Inspection -> Bridge Overpass -> Home Base.
        """
        print("[Mock Engine] Starting Mission-Based 3D Flight Simulation Loop @ 30 FPS...")
        fps = 30.0
        dt = 1.0 / fps

        # Drone simulated physical state
        pos = np.array([726.03, 18.93, 101.91], dtype=float)
        current_yaw = 0.0
        current_roll = 0.0
        current_pitch = 0.0
        sim_time = 0.0
        mission_restart_timer = 0

        while True:
            t0 = time.perf_counter()
            self.frame_counter += 1
            sim_time += dt

            # 1. Compute autonomous flight command from WaypointNavigator
            flight_cmd = self.engine.guidance.compute_flight_command(pos, current_yaw)
            speed = float(flight_cmd.get("desired_velocity_mps", 0.0))
            target_yaw = float(flight_cmd.get("target_heading_yaw_deg", 0.0))
            target_roll = float(flight_cmd.get("target_roll_deg", 0.0))
            target_pitch = float(flight_cmd.get("target_pitch_deg", 0.0))
            climb_rate = float(flight_cmd.get("climb_rate_mps", 0.0))
            status = flight_cmd.get("mission_status", "NAVIGATING")

            # 2. Smooth 6-DOF Rotational Dynamics
            yaw_diff = (target_yaw - current_yaw + 180.0) % 360.0 - 180.0
            current_yaw = (current_yaw + yaw_diff * 0.12) % 360.0
            current_roll += (target_roll - current_roll) * 0.15
            current_pitch += (target_pitch - current_pitch) * 0.15

            # 3. 3D Kinematic Position Propagation
            yaw_rad = math.radians(current_yaw)
            vx = speed * math.cos(yaw_rad)
            vy = speed * math.sin(yaw_rad)
            vz = climb_rate

            pos[0] += vx * dt
            pos[1] += vy * dt
            pos[2] += vz * dt

            # 4. Handle Mission Completion & Auto-Restart
            if status == "MISSION_COMPLETED":
                mission_restart_timer += 1
                if mission_restart_timer > 90:  # Pause 3 seconds at landing, then restart
                    self.engine.guidance.reset()
                    pos = np.array([726.03, 18.93, 101.91], dtype=float)
                    current_yaw = 0.0
                    mission_restart_timer = 0
                    print("[Mock SLAM] Mission completed! Restarting mission cycle...")

            # 5. Inject Realistic Sensor Measurement Noise
            est_x = round(float(pos[0]) + float(np.random.normal(0, 0.02)), 3)
            est_y = round(float(pos[1]) + float(np.random.normal(0, 0.02)), 3)
            est_z = round(float(pos[2]) + float(np.random.normal(0, 0.015)), 3)

            confidence = round(float(np.random.uniform(0.96, 0.99)), 2)
            proc_time_ms = round(float(np.random.uniform(0.3, 0.6)), 2)

            p4_packet = {
                "frame_id": self.frame_counter,
                "timestamp": round(sim_time, 4),
                "estimated_pose": {
                    "x": est_x,
                    "y": est_y,
                    "z": est_z,
                    "roll": round(float(current_roll), 2),
                    "pitch": round(float(current_pitch), 2),
                    "yaw": round(float(current_yaw), 2),
                },
                "velocity": {
                    "x": round(float(vx), 3),
                    "y": round(float(vy), 3),
                    "z": round(float(vz), 3),
                },
                "tracking_state": "TRACKING_GOOD",
                "confidence": confidence,
                "processing_time_ms": proc_time_ms,
                "flight_command": flight_cmd
            }

            output_packet = dict(p4_packet)
            self.latest_output_packet = output_packet

            # Push to P4 Streamer Queue
            try:
                if self.p4_queue.full():
                    self.p4_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.p4_queue.put_nowait(json.dumps(p4_packet))
            except asyncio.QueueFull:
                pass

            # Optional Live Cockpit Window
            if self.enable_view:
                self.render_live_view(None, output_packet)

            # Broadcast to local telemetry clients
            if self.telemetry_clients:
                telemetry_json = json.dumps(output_packet)
                await asyncio.gather(*[
                    client.send(telemetry_json)
                    for client in list(self.telemetry_clients)
                ], return_exceptions=True)

            if self.frame_counter % 15 == 0:
                p4_str = "[P4 Stream: OK]" if self.p4_connected else "[P4 Stream: Waiting]"
                wp_idx = flight_cmd.get("active_waypoint_idx", "-")
                wp_name = flight_cmd.get("active_waypoint_name", "")
                dist = flight_cmd.get("distance_to_waypoint_m", 0.0)
                print(f"[Mock Mission] Frame #{self.frame_counter:04d} | Pos: ({est_x:.2f}, {est_y:.2f}, {est_z:.2f}) m | Target WP #{wp_idx} ({wp_name}) | Dist: {dist:.1f}m | {p4_str}")

            dt_actual = time.perf_counter() - t0
            sleep_time = max(0.001, dt - dt_actual)
            await asyncio.sleep(sleep_time)

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

                    # Build exact P4 JSON payload matching to_see.md specification
                    flight_cmd = output_packet.get("flight_command", {})
                    p4_packet = {
                        "frame_id": int(output_packet["frame_id"]),
                        "timestamp": float(output_packet["timestamp"]),
                        "estimated_pose": {
                            "x": float(output_packet["estimated_pose"]["x"]),
                            "y": float(output_packet["estimated_pose"]["y"]),
                            "z": float(output_packet["estimated_pose"]["z"]),
                            "roll": float(output_packet["estimated_pose"]["roll"]),
                            "pitch": float(output_packet["estimated_pose"]["pitch"]),
                            "yaw": float(output_packet["estimated_pose"]["yaw"]),
                        },
                        "velocity": {
                            "x": float(output_packet["velocity"]["x"]),
                            "y": float(output_packet["velocity"]["y"]),
                            "z": float(output_packet["velocity"]["z"]),
                        },
                        "tracking_state": str(output_packet["tracking_state"]),
                        "confidence": float(output_packet["confidence"]),
                        "processing_time_ms": round(float(dt_ms), 2),
                        "flight_command": flight_cmd
                    }

                    # Non-blocking push to P4 WebSocket streamer
                    try:
                        if self.p4_queue.full():
                            self.p4_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        self.p4_queue.put_nowait(json.dumps(p4_packet))
                    except asyncio.QueueFull:
                        pass

                    # Optional Live Cockpit Window
                    if self.enable_view:
                        frame_img = self.engine._load_camera_frame(data.get("camera", {}))
                        self.render_live_view(frame_img, output_packet)

                    # Send autonomous flight command back to Blender (The Pilot)
                    response = {
                        "frame_id": output_packet["frame_id"],
                        "flight_command": flight_cmd,
                        "latency_ms": round(dt_ms, 2)
                    }
                    await websocket.send(json.dumps(response))

                    # Broadcast estimated pose to local telemetry subscribers
                    if self.telemetry_clients:
                        telemetry_json = json.dumps(output_packet)
                        await asyncio.gather(*[
                            client.send(telemetry_json)
                            for client in list(self.telemetry_clients)
                        ], return_exceptions=True)

                    if self.frame_counter % 15 == 0:
                        pose = output_packet["estimated_pose"]
                        p4_str = "[P4 Stream: OK]" if self.p4_connected else "[P4 Stream: Waiting]"
                        print(f"[Pilot] Frame #{self.frame_counter:04d} | Pos: ({pose['x']:.2f}, {pose['y']:.2f}, {pose['z']:.2f}) m | Target WP: {flight_cmd.get('active_waypoint_idx')} ({flight_cmd.get('active_waypoint_name')}) | Latency: {dt_ms:.1f}ms | {p4_str}")

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
        """Starts the WebSocket server, P4 forwarder and camera consumer loops."""
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
        print(f"  • P4 Direct Stream Target: {self.p4_ws_url}")
        print(f"  • P4 Binary Camera Source: ws://{self.p4_ip}:{self.p4_video_port}/ws/slam")
        if self.enable_mock:
            print(f"  • Mission Mock Mode:       ENABLED (Autonomous Waypoints)")
        if self.enable_view:
            print(f"  • Live Cockpit HUD Window: ENABLED")
        print("=" * 65 + "\n")

        # Start P4 background tasks
        asyncio.create_task(self.p4_forwarder_loop())
        asyncio.create_task(self.p4_camera_consumer_loop())

        # If mock mode enabled, start internal mission flight loop
        if self.enable_mock:
            asyncio.create_task(self.mock_simulation_loop())

        async with websockets.serve(
            self.router,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=20,
            max_size=10_000_000
        ):
            await asyncio.Future()  # run forever


def main():
    parser = argparse.ArgumentParser(description="Navis Real-Time Telemetry Bridge Server.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port number (default: 8765)")
    parser.add_argument("--p4-ip", type=str, default="10.110.7.40", help="P4 Backend IP (default: 10.110.7.40)")
    parser.add_argument("--p4-port", type=int, default=8004, help="P4 Navigation WebSocket port (default: 8004)")
    parser.add_argument("--p4-video-port", type=int, default=8000, help="P4 Video port (default: 8000)")
    parser.add_argument("--waypoints", type=str, default=None, help="Path to mission waypoints JSON")
    parser.add_argument("--view", action="store_true", help="Enable Live Cockpit HUD Video Window")
    parser.add_argument("--mock", action="store_true", help="Run in Mock Mode (Simulates 3D mission waypoint flight)")

    args = parser.parse_args()

    default_wp = os.path.join(root_dir, "navigation", "configs", "mission_waypoints.json")
    wp_path = args.waypoints if args.waypoints else (default_wp if os.path.exists(default_wp) else None)

    server = NavigationStreamServer(
        host=args.host,
        port=args.port,
        p4_ip=args.p4_ip,
        p4_port=args.p4_port,
        p4_video_port=args.p4_video_port,
        waypoints_file=wp_path,
        enable_view=args.view,
        enable_mock=args.mock
    )
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Server] Shutdown signal received. Closing server.")
        if args.view:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
