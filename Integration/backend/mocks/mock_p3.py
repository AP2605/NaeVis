"""Mock P3 Navigation Producer.

Simulates P3 Navigation Engine (INS + VIO / Visual SLAM) by estimating 6-DoF pose,
3D linear velocity, tracking health, confidence, and computation latency,
and transmitting state packets to P4 integration backend over REST.
"""

import argparse
import asyncio
import math
import random
import time
import httpx


class MockP3Producer:
    """Simulates P3 Navigation Engine estimated state outputs."""

    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        fps: float = 20.0,
        total_frames: int = 0,
        noise_level: float = 0.05,
    ):
        self.target_url = target_url.rstrip("/")
        self.fps = fps
        self.interval = 1.0 / max(fps, 0.1)
        self.total_frames = total_frames
        self.noise_level = noise_level
        self.frame_id = 0
        self.start_time = time.time()

        self.base_x = 0.0
        self.base_y = 0.0
        self.base_z = 20.0

    def generate_packet(self) -> dict:
        """Generate realistic P3 navigation estimation packet."""
        self.frame_id += 1
        elapsed = time.time() - self.start_time
        sim_time = round(elapsed, 3)

        # Estimated path with slight estimation drift / noise
        radius = 25.0
        ang_speed = 0.15
        true_x = self.base_x + radius * math.sin(elapsed * ang_speed)
        true_y = self.base_y + radius * math.sin(elapsed * ang_speed * 2) * 0.6
        true_z = self.base_z + 3.0 * math.sin(elapsed * 0.2)

        est_x = round(true_x + random.gauss(0, self.noise_level), 3)
        est_y = round(true_y + random.gauss(0, self.noise_level), 3)
        est_z = round(true_z + random.gauss(0, self.noise_level * 0.5), 3)

        # Estimated attitude in degrees
        roll = round(math.sin(elapsed * 0.4) * 4.0 + random.gauss(0, 0.2), 2)
        pitch = round(math.cos(elapsed * 0.4) * 3.0 + random.gauss(0, 0.2), 2)
        yaw = round(((math.degrees(elapsed * ang_speed) + 90.0) % 360.0) + random.gauss(0, 0.5), 2)

        # Estimated linear velocity vector in m/s
        vx = round(radius * ang_speed * math.cos(elapsed * ang_speed) + random.gauss(0, 0.05), 2)
        vy = round(radius * ang_speed * 1.2 * math.cos(elapsed * ang_speed * 2) + random.gauss(0, 0.05), 2)
        vz = round(0.6 * math.cos(elapsed * 0.2) + random.gauss(0, 0.02), 2)

        # Tracking state (primarily GOOD, occasionally slight degradation if simulated)
        tracking_state = "TRACKING_GOOD"
        confidence = round(random.uniform(0.92, 0.98), 2)
        latency_ms = round(random.uniform(14.0, 22.0), 1)

        packet = {
            "frame_id": self.frame_id,
            "timestamp": sim_time,
            "estimated_pose": {
                "x": est_x,
                "y": est_y,
                "z": est_z,
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
            "processing_time_ms": latency_ms,
        }
        return packet

    async def run(self):
        """Run the mock P3 navigation publishing loop."""
        url = f"{self.target_url}/api/v1/navigation/state"
        print(f"[Mock P3] Starting Navigation Estimation stream -> {url} @ {self.fps} FPS")

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
                                f"[Mock P3] Ingested frame={packet['frame_id']} | "
                                f"est=({packet['estimated_pose']['x']:.2f}, {packet['estimated_pose']['y']:.2f}, {packet['estimated_pose']['z']:.2f}) | "
                                f"conf={packet['confidence']:.2f}"
                            )
                    else:
                        print(f"[Mock P3] Server returned {resp.status_code}: {resp.text}")
                except Exception as exc:
                    print(f"[Mock P3] Send failed: {exc}")

                count += 1
                elapsed = time.time() - loop_start
                sleep_time = max(0.0, self.interval - elapsed)
                await asyncio.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(description="Mock P3 Navigation State Producer")
    parser.add_argument("--target", default="http://localhost:8000", help="Target P4 Backend URL")
    parser.add_argument("--fps", type=float, default=20.0, help="Publishing rate in Hz")
    parser.add_argument("--frames", type=int, default=0, help="Total frames to publish (0 for infinite)")
    parser.add_argument("--noise", type=float, default=0.05, help="Simulated pose estimation noise stddev")
    args = parser.parse_args()

    producer = MockP3Producer(
        target_url=args.target,
        fps=args.fps,
        total_frames=args.frames,
        noise_level=args.noise,
    )
    asyncio.run(producer.run())


if __name__ == "__main__":
    main()
