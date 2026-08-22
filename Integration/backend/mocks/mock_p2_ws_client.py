"""Mock P2 Simulation Ground Truth Telemetry WebSocket Client.

Connects to the P4 Backend on port 8000 (/ws/telemetry?role=producer)
and streams simulated 6-DoF ground truth telemetry packets matching the exact P2 data contract.
"""

import argparse
import asyncio
import json
import math
import random
import sys
import time
import websockets


class MockP2WebSocketClient:
    """Simulates real-time P2 simulation ground-truth telemetry over WebSocket."""

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:8005/ws/telemetry",
        fps: float = 20.0,
        total_frames: int = 0,
        source: str = "mock",
    ):
        if "?" not in ws_url:
            ws_url = f"{ws_url}?source={source}"
        elif "source=" not in ws_url:
            ws_url = f"{ws_url}&source={source}"
        self.ws_url = ws_url
        self.fps = fps
        self.interval = 1.0 / max(fps, 0.1)
        self.total_frames = total_frames
        self.frame_id = 0
        self.start_time = time.time()

    def generate_packet(self) -> dict:
        """Generate realistic 6-DoF ground truth telemetry packet."""
        self.frame_id += 1
        elapsed = time.time() - self.start_time
        sim_time = round(elapsed, 3)

        # Smooth simulation ground truth trajectory
        x = round(math.sin(elapsed * 0.2) * 25.0 + (elapsed * 1.5), 3)
        y = round(math.cos(elapsed * 0.2) * 15.0, 3)
        z = round(10.0 + math.sin(elapsed * 0.1) * 2.0, 3)

        vx = round(1.5, 2)
        vy = round(0.0, 2)
        vz = round(0.0, 2)

        roll = round(math.sin(elapsed * 0.5) * 3.0, 2)
        pitch = round(math.cos(elapsed * 0.5) * 2.0, 2)
        yaw = round((elapsed * 5.0) % 360.0, 2)

        return {
            "frame_id": self.frame_id,
            "timestamp": sim_time,
            "ground_truth": {
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
            "lidar": {
                "front": round(random.uniform(15.0, 25.0), 2),
                "bottom": round(z, 2),
            },
        }

    async def run(self):
        """Run the mock P2 telemetry streaming loop."""
        print("=" * 65)
        print("  SIH-NAVIS Mock P2 Ground Truth WebSocket Client")
        print("=" * 65)
        print(f"  Target WebSocket: {self.ws_url}")
        print(f"  Rate:             {self.fps} Hz")
        print(f"  Frame Limit:      {'Infinite' if self.total_frames == 0 else self.total_frames}")
        print("=" * 65)

        retry_count = 0
        while True:
            try:
                print(f"[Mock P2 Client] Connecting to {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    print(f"[Mock P2 Client] Connected! Streaming ground truth at {self.fps} Hz...")
                    retry_count = 0
                    count = 0

                    while self.total_frames == 0 or count < self.total_frames:
                        loop_start = time.perf_counter()
                        packet = self.generate_packet()
                        packet_str = json.dumps(packet)

                        await ws.send(packet_str)
                        count += 1

                        if self.frame_id % 20 == 0:
                            gt = packet["ground_truth"]
                            print(
                                f"[Mock P2 Client] Sent frame #{self.frame_id:04d} | "
                                f"GT Pos: ({gt['x']:.1f}, {gt['y']:.1f}, {gt['z']:.1f}) m | "
                                f"Att: ({gt['roll']:.1f}, {gt['pitch']:.1f}, {gt['yaw']:.1f})°"
                            )

                        elapsed = time.perf_counter() - loop_start
                        sleep_time = max(0.0, self.interval - elapsed)
                        await asyncio.sleep(sleep_time)

                    print(f"[Mock P2 Client] Completed streaming {count} frames.")
                    break

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as err:
                retry_count += 1
                if retry_count > 10 and self.total_frames > 0:
                    print(f"[Mock P2 Client] Max retries reached. Exiting: {err}")
                    break
                print(f"[Mock P2 Client] Server disconnected / offline ({err}). Retrying in 2.0s...")
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                print("\n[Mock P2 Client] Stream cancelled by user.")
                break


def main():
    parser = argparse.ArgumentParser(description="Mock P2 Simulation Ground Truth Telemetry WebSocket Client")
    parser.add_argument("--url", default="ws://127.0.0.1:8005/ws/telemetry", help="Target WebSocket URL")
    parser.add_argument("--fps", type=float, default=20.0, help="Packet rate in Hz")
    parser.add_argument("--frames", type=int, default=0, help="Total frames to send (0 for infinite)")
    parser.add_argument("--source", default="mock", choices=["mock", "real"], help="Source provenance flag")
    args = parser.parse_args()

    client = MockP2WebSocketClient(
        ws_url=args.url,
        fps=args.fps,
        total_frames=args.frames,
        source=args.source,
    )
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n[Mock P2 Client] Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
