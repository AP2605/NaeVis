"""Mock P2 Simulation Ground Truth Producer.

Simulates Blender Simulation Ground Truth stream by generating true 6-DoF poses,
orientation angles, LiDAR range readings, and camera image metadata,
and sending them to P4 integration backend over REST.
"""

import argparse
import asyncio
import math
import random
import time
import httpx


class MockP2Producer:
    """Simulates P2 Blender simulation ground truth outputs."""

    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        fps: float = 20.0,
        total_frames: int = 0,
    ):
        self.target_url = target_url.rstrip("/")
        self.fps = fps
        self.interval = 1.0 / max(fps, 0.1)
        self.total_frames = total_frames
        self.frame_id = 0
        self.start_time = time.time()

        # Flight trajectory parameters (smooth 3D path)
        self.base_x = 0.0
        self.base_y = 0.0
        self.base_z = 20.0
        self.flight_speed = 4.0  # m/s

    def generate_packet(self) -> dict:
        """Generate realistic P2 simulation ground truth packet."""
        self.frame_id += 1
        elapsed = time.time() - self.start_time
        sim_time = round(elapsed, 3)

        # 3D curve / waypoint loop trajectory
        radius = 25.0
        ang_speed = 0.15
        cur_x = round(self.base_x + radius * math.sin(elapsed * ang_speed), 3)
        cur_y = round(self.base_y + radius * math.sin(elapsed * ang_speed * 2) * 0.6, 3)
        cur_z = round(self.base_z + 3.0 * math.sin(elapsed * 0.2), 3)

        # True attitude (roll, pitch, yaw) in degrees
        roll = round(math.sin(elapsed * 0.4) * 4.0, 2)
        pitch = round(math.cos(elapsed * 0.4) * 3.0, 2)
        yaw = round((math.degrees(elapsed * ang_speed) + 90.0) % 360.0, 2)

        # Simulated LiDAR distance rays
        lidar_bottom = max(1.0, round(cur_z - 0.5 + random.uniform(-0.1, 0.1), 2))
        lidar_front = max(2.0, round(18.0 + 5.0 * math.sin(elapsed * 0.3) + random.uniform(-0.2, 0.2), 2))
        lidar_front_left = max(2.0, round(22.0 + 4.0 * math.cos(elapsed * 0.3) + random.uniform(-0.2, 0.2), 2))
        lidar_front_right = max(2.0, round(16.0 + 4.0 * math.sin(elapsed * 0.2) + random.uniform(-0.2, 0.2), 2))

        packet = {
            "timestamp": sim_time,
            "frame_id": self.frame_id,
            "position": {
                "x": cur_x,
                "y": cur_y,
                "z": cur_z,
            },
            "orientation": {
                "roll": roll,
                "pitch": pitch,
                "yaw": yaw,
            },
            "lidar": {
                "front": lidar_front,
                "front_left": lidar_front_left,
                "front_right": lidar_front_right,
                "bottom": lidar_bottom,
            },
            "camera": {
                "frame_id": self.frame_id,
                "image_path": f"frames/frame_{self.frame_id:04d}.png",
                "timestamp": sim_time,
                "width": 640,
                "height": 480,
            },
        }
        return packet

    async def run(self):
        """Run the mock P2 ground truth publishing loop."""
        url = f"{self.target_url}/api/v1/simulation/ground-truth"
        print(f"[Mock P2] Starting Simulation Ground Truth stream -> {url} @ {self.fps} FPS")

        async with httpx.AsyncClient(timeout=5.0) as client:
            count = 0
            while self.total_frames == 0 or count < self.total_frames:
                loop_start = time.time()
                packet = self.generate_packet()
                try:
                    resp = await client.post(url, json=packet)
                    if resp.status_code == 200:
                        if self.frame_id % 20 == 0:
                            print(
                                f"[Mock P2] Ingested frame={packet['frame_id']} | "
                                f"pos=({packet['position']['x']:.2f}, {packet['position']['y']:.2f}, {packet['position']['z']:.2f})"
                            )
                    else:
                        print(f"[Mock P2] Server returned {resp.status_code}: {resp.text}")
                except Exception as exc:
                    print(f"[Mock P2] Send failed: {exc}")

                count += 1
                elapsed = time.time() - loop_start
                sleep_time = max(0.0, self.interval - elapsed)
                await asyncio.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(description="Mock P2 Simulation Ground Truth Producer")
    parser.add_argument("--target", default="http://localhost:8000", help="Target P4 Backend URL")
    parser.add_argument("--fps", type=float, default=20.0, help="Publishing rate in Hz")
    parser.add_argument("--frames", type=int, default=0, help="Total frames to publish (0 for infinite)")
    args = parser.parse_args()

    producer = MockP2Producer(target_url=args.target, fps=args.fps, total_frames=args.frames)
    asyncio.run(producer.run())


if __name__ == "__main__":
    main()
