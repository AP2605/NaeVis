"""Mock P3 Navigation WebSocket Client.

Connects to the dedicated P4 Navigation WebSocket Server on port 8004 (/ws/navigation)
and streams simulated 6-DoF navigation estimation packets matching the exact P3 data contract.
"""

import argparse
import asyncio
import json
import math
import random
import sys
import time
import websockets


class MockP3WebSocketClient:
    """Simulates real-time P3 SLAM / navigation telemetry over WebSocket."""

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:8004/ws/navigation",
        fps: float = 20.0,
        total_frames: int = 0,
        source: str = "mock",
    ):
        # Append source query parameter if not present
        if "?" not in ws_url:
            ws_url = f"{ws_url}?source={source}"
        self.ws_url = ws_url
        self.fps = fps
        self.interval = 1.0 / max(fps, 0.1)
        self.total_frames = total_frames
        self.frame_id = 0
        self.start_time = time.time()

    def generate_packet(self) -> dict:
        """Generate realistic 6-DoF navigation estimation packet matching exact contract."""
        self.frame_id += 1
        elapsed = time.time() - self.start_time
        sim_time = round(elapsed, 3)

        # Smooth flight trajectory
        x = round(math.sin(elapsed * 0.2) * 25.0 + (elapsed * 1.5), 3)
        y = round(math.cos(elapsed * 0.2) * 15.0, 3)
        z = round(10.0 + math.sin(elapsed * 0.1) * 2.0, 3)

        vx = round(1.5 + random.uniform(-0.1, 0.1), 2)
        vy = round(random.uniform(-0.05, 0.05), 2)
        vz = round(random.uniform(-0.02, 0.02), 2)

        roll = round(math.sin(elapsed * 0.5) * 3.0, 2)
        pitch = round(math.cos(elapsed * 0.5) * 2.0, 2)
        yaw = round((elapsed * 5.0) % 360.0, 2)

        confidence = round(random.uniform(0.92, 0.99), 2)
        tracking_state = "TRACKING_GOOD" if confidence > 0.85 else "TRACKING_DEGRADED"

        return {
            "frame_id": self.frame_id,
            "timestamp": sim_time,
            "estimated_pose": {
                "x": x,
                "y": y,
                "z": z,
                "roll": roll,
                "pitch": pitch,
                "yaw": yaw,
            },
            "velocity": {
                "x": vx,
                "y": vy,
                "z": vz,
            },
            "tracking_state": tracking_state,
            "confidence": confidence,
            "processing_time_ms": round(random.uniform(0.3, 0.8), 2),
        }

    async def run(self):
        """Run the mock P3 streaming client loop."""
        print("=" * 65)
        print("  SIH-NAVIS Mock P3 Navigation WebSocket Client")
        print("=" * 65)
        print(f"  Target WebSocket: {self.ws_url}")
        print(f"  Rate:             {self.fps} Hz")
        print(f"  Frame Limit:      {'Infinite' if self.total_frames == 0 else self.total_frames}")
        print("=" * 65)

        retry_count = 0
        while True:
            try:
                print(f"[Mock P3 Client] Connecting to {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    print(f"[Mock P3 Client] Connected successfully! Streaming navigation packets at {self.fps} Hz...")
                    retry_count = 0
                    count = 0

                    while self.total_frames == 0 or count < self.total_frames:
                        loop_start = time.perf_counter()
                        packet = self.generate_packet()
                        packet_str = json.dumps(packet)

                        await ws.send(packet_str)
                        count += 1

                        if self.frame_id % 20 == 0:
                            pose = packet["estimated_pose"]
                            print(
                                f"[Mock P3 Client] Sent frame #{self.frame_id:04d} | "
                                f"Pos: ({pose['x']:.1f}, {pose['y']:.1f}, {pose['z']:.1f}) m | "
                                f"Conf: {packet['confidence']:.2f}"
                            )

                        elapsed = time.perf_counter() - loop_start
                        sleep_time = max(0.0, self.interval - elapsed)
                        await asyncio.sleep(sleep_time)

                    print(f"[Mock P3 Client] Completed streaming {count} frames.")
                    break

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as err:
                retry_count += 1
                if retry_count > 10 and self.total_frames > 0:
                    print(f"[Mock P3 Client] Max retries reached. Exiting: {err}")
                    break
                print(f"[Mock P3 Client] Server offline / disconnected ({err}). Retrying in 2.0s...")
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                print("\n[Mock P3 Client] Stream cancelled by user.")
                break


def main():
    parser = argparse.ArgumentParser(description="Mock P3 Navigation WebSocket Client")
    parser.add_argument("--url", default="ws://127.0.0.1:8004/ws/navigation", help="Target WebSocket URL")
    parser.add_argument("--fps", type=float, default=20.0, help="Navigation packet rate in Hz")
    parser.add_argument("--frames", type=int, default=0, help="Total frames to send (0 for infinite)")
    parser.add_argument("--source", default="mock", choices=["mock", "real"], help="Source provenance flag")
    args = parser.parse_args()

    client = MockP3WebSocketClient(
        ws_url=args.url,
        fps=args.fps,
        total_frames=args.frames,
        source=args.source,
    )
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n[Mock P3 Client] Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
