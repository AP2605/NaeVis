"""Mock P1 Perception Producer.

Simulates P1 ML Perception pipeline by sending structured vision inference packets
(terrain classification, segmentation, landmarks, place recognition, hints)
to the P4 integration backend over REST.
"""

import argparse
import asyncio
import math
import random
import time
import httpx


class MockP1Producer:
    """Simulates P1 ML / Perception outputs."""

    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        fps: float = 5.0,
        total_frames: int = 0,
    ):
        self.target_url = target_url.rstrip("/")
        self.fps = fps
        self.interval = 1.0 / max(fps, 0.1)
        self.total_frames = total_frames
        self.frame_id = 0
        self.start_time = time.time()

        self.terrain_types = ["urban", "suburban", "forest", "industrial", "runway", "barren"]
        self.landmark_classes = ["building_corner", "road_intersection", "communication_tower", "bridge", "roundabout"]

    def generate_packet(self) -> dict:
        """Generate realistic P1 perception packet."""
        self.frame_id += 1
        elapsed = time.time() - self.start_time
        sim_time = round(elapsed, 3)

        terrain_idx = int(elapsed / 15.0) % len(self.terrain_types)
        terrain_type = self.terrain_types[terrain_idx]

        # Dynamic landmarks
        num_landmarks = random.randint(1, 4)
        landmarks = []
        for i in range(num_landmarks):
            label = random.choice(self.landmark_classes)
            lm_x = round(10.0 + math.sin(elapsed + i) * 15.0 + random.uniform(-0.5, 0.5), 2)
            lm_y = round(5.0 + math.cos(elapsed + i) * 12.0 + random.uniform(-0.5, 0.5), 2)
            lm_z = round(-5.0 + random.uniform(-1.0, 1.0), 2)
            landmarks.append({
                "landmark_id": f"LM_{self.frame_id % 20}_{i+1}",
                "label": label,
                "confidence": round(random.uniform(0.85, 0.98), 2),
                "bbox": [
                    round(random.uniform(50, 150), 1),
                    round(random.uniform(50, 150), 1),
                    round(random.uniform(200, 300), 1),
                    round(random.uniform(200, 300), 1),
                ],
                "estimated_relative_pos": {
                    "x": lm_x,
                    "y": lm_y,
                    "z": lm_z,
                },
            })

        # Place recognition match every ~10 frames
        has_place_match = (self.frame_id % 8 == 0)

        # Visual localization correction hint
        corr_x = round(random.uniform(-0.15, 0.15), 3)
        corr_y = round(random.uniform(-0.15, 0.15), 3)
        corr_z = round(random.uniform(-0.05, 0.05), 3)

        packet = {
            "frame_id": self.frame_id,
            "timestamp": sim_time,
            "terrain": {
                "terrain_type": terrain_type,
                "confidence": round(random.uniform(0.88, 0.99), 2),
                "roughness": round(random.uniform(0.05, 0.25), 2),
                "features": ["flat_ground", "structures"] if terrain_type == "urban" else ["canopy", "vegetation"],
            },
            "segmentation": {
                "classes": ["building", "road", "vegetation", "sky"],
                "mask_path": f"masks/seg_frame_{self.frame_id:04d}.png",
                "coverage_percentages": {
                    "building": round(random.uniform(20.0, 45.0), 1),
                    "road": round(random.uniform(15.0, 30.0), 1),
                    "vegetation": round(random.uniform(10.0, 25.0), 1),
                    "sky": round(random.uniform(10.0, 20.0), 1),
                },
            },
            "landmarks": landmarks,
            "place_recognition": {
                "match_found": has_place_match,
                "location_id": f"WP_NODE_{(self.frame_id // 10) + 1}" if has_place_match else None,
                "similarity_score": round(random.uniform(0.82, 0.96), 2) if has_place_match else 0.0,
                "reference_coordinates": {
                    "x": round(100.0 + self.frame_id * 0.5, 2),
                    "y": round(50.0 + self.frame_id * 0.2, 2),
                    "z": 25.0,
                } if has_place_match else None,
            },
            "terrain_match": {
                "matched": True,
                "elevation_estimate": round(25.0 + math.sin(elapsed * 0.1) * 3.0, 2),
                "map_tile_id": f"tile_dem_{(self.frame_id // 50):03d}",
                "correlation_score": round(random.uniform(0.86, 0.97), 2),
            },
            "mission_awareness": {
                "threat_detected": False,
                "landing_zone_viable": True,
                "notes": "Nominal flight corridor",
            },
            "visual_localization_hint": {
                "suggested_correction": {
                    "x": corr_x,
                    "y": corr_y,
                    "z": corr_z,
                },
                "uncertainty_radius": round(random.uniform(0.3, 0.8), 2),
                "hint_confidence": round(random.uniform(0.80, 0.94), 2),
            },
            "system": {
                "model_version": "yolov8-seg-sih-v1",
                "inference_time_ms": round(random.uniform(22.0, 38.0), 1),
                "device": "cuda:0",
                "gpu_utilization_pct": round(random.uniform(55.0, 75.0), 1),
            },
        }
        return packet

    async def run(self):
        """Run the mock P1 producer publishing loop."""
        url = f"{self.target_url}/api/v1/perception/result"
        print(f"[Mock P1] Starting Perception stream -> {url} @ {self.fps} FPS")

        async with httpx.AsyncClient(timeout=5.0) as client:
            count = 0
            while self.total_frames == 0 or count < self.total_frames:
                loop_start = time.time()
                packet = self.generate_packet()
                try:
                    resp = await client.post(url, json=packet)
                    if resp.status_code == 200:
                        if self.frame_id % 10 == 0:
                            print(f"[Mock P1] Ingested frame={packet['frame_id']} | terrain={packet['terrain']['terrain_type']}")
                    else:
                        print(f"[Mock P1] Server returned {resp.status_code}: {resp.text}")
                except Exception as exc:
                    print(f"[Mock P1] Send failed: {exc}")

                count += 1
                elapsed = time.time() - loop_start
                sleep_time = max(0.0, self.interval - elapsed)
                await asyncio.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(description="Mock P1 Perception Producer")
    parser.add_argument("--target", default="http://localhost:8000", help="Target P4 Backend URL")
    parser.add_argument("--fps", type=float, default=5.0, help="Perception publishing rate in Hz")
    parser.add_argument("--frames", type=int, default=0, help="Total frames to publish (0 for infinite)")
    args = parser.parse_args()

    producer = MockP1Producer(target_url=args.target, fps=args.fps, total_frames=args.frames)
    asyncio.run(producer.run())


if __name__ == "__main__":
    main()
