"""End-to-End M4 Demonstration Script for SIH-NAVIS.

Demonstrates complete M4 pipeline:
1. Creates mission with Source (0,0,10), Waypoints [(20,10,15), (40,30,18), (70,40,20)], Destination (100,50,20).
2. Starts the mission, transmitting to P3 and transitioning to ACTIVE.
3. Streams synchronized P2 Ground Truth and P3 Navigation Pose with realistic flight dynamics.
4. Streams RGB camera frames to the live viewer.
5. Displays real-time 3D localization error, ATE, RPE, drift, and waypoint advancement.
"""

import argparse
import asyncio
import math
import random
import time
import httpx

from mocks.mock_camera import MockCameraProducer
from mocks.mock_p1 import MockP1Producer


def interpolate_points(p0: dict, p1: dict, alpha: float) -> dict:
    """Linear interpolation between two 3D positions."""
    return {
        "x": round(p0["x"] + (p1["x"] - p0["x"]) * alpha, 3),
        "y": round(p0["y"] + (p1["y"] - p0["y"]) * alpha, 3),
        "z": round(p0["z"] + (p1["z"] - p0["z"]) * alpha, 3),
    }


class M4MissionDemoRunner:
    """Runs autonomous mission simulation following defined waypoints."""

    def __init__(self, target_url: str = "http://localhost:8000", fps: float = 15.0):
        self.target_url = target_url.rstrip("/")
        self.fps = fps
        self.interval = 1.0 / max(fps, 1.0)
        self.mission_id: str | None = None

        # Mission Waypoints Route
        self.route = [
            {"x": 0.0, "y": 0.0, "z": 10.0, "name": "SOURCE"},
            {"x": 20.0, "y": 10.0, "z": 15.0, "name": "WP-1"},
            {"x": 40.0, "y": 30.0, "z": 18.0, "name": "WP-2"},
            {"x": 70.0, "y": 40.0, "z": 20.0, "name": "WP-3"},
            {"x": 100.0, "y": 50.0, "z": 20.0, "name": "DESTINATION"},
        ]

    async def setup_mission(self, client: httpx.AsyncClient) -> str:
        """Create and start mission via backend REST API."""
        print("\n=======================================================")
        print(" [M4 DEMO] Step 1: Defining & Creating Mission")
        print("=======================================================")

        payload = {
            "mission_name": "Forest Inspection & Mapping M4",
            "source": self.route[0],
            "waypoints": [
                {"x": w["x"], "y": w["y"], "z": w["z"], "name": w["name"]}
                for w in self.route[1:-1]
            ],
            "destination": self.route[-1],
            "coordinate_frame": "BLENDER_LOCAL",
        }

        res = await client.post(f"{self.target_url}/api/v1/missions", json=payload)
        if res.status_code != 201:
            raise RuntimeError(f"Failed to create mission: {res.text}")

        data = res.json()
        self.mission_id = data["mission_id"]
        print(f" [+] Mission Created: '{data['mission_name']}' (ID: {self.mission_id})")
        print(f" [+] Source: ({data['source']['x']}, {data['source']['y']}, {data['source']['z']})")
        print(f" [+] Waypoints Count: {len(data['waypoints'])}")
        print(f" [+] Destination: ({data['destination']['x']}, {data['destination']['y']}, {data['destination']['z']})")

        # Start Mission
        print("\n=======================================================")
        print(" [M4 DEMO] Step 2: Transmitting to P3 & Starting Mission")
        print("=======================================================")
        start_res = await client.post(f"{self.target_url}/api/v1/missions/{self.mission_id}/start")
        if start_res.status_code != 200:
            raise RuntimeError(f"Failed to start mission: {start_res.text}")
        print(f" [+] Mission Started -> Status: ACTIVE")
        return self.mission_id

    async def run_flight_simulation(self, enable_camera: bool = True, enable_p1: bool = True, keep_alive_sec: float = 5.0):
        """Simulate drone flight traversing waypoints with synchronized GT, EST, P1, and Camera telemetry."""
        cam_task: asyncio.Task | None = None
        p1_task: asyncio.Task | None = None

        if enable_camera:
            cam_ws = self.target_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/camera?role=producer"
            cam_producer = MockCameraProducer(ws_url=cam_ws, fps=15.0)
            cam_task = asyncio.create_task(cam_producer.run())
            print(f" [+] Live Camera Producer launched ({cam_ws} @ 15 FPS)")

        if enable_p1:
            p1_producer = MockP1Producer(target_url=self.target_url, fps=5.0)
            p1_task = asyncio.create_task(p1_producer.run())
            print(f" [+] Live P1 Perception Producer launched (5 Hz)")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await self.setup_mission(client)

                print("\n=======================================================")
                print(" [M4 DEMO] Step 3: Streaming Flight Telemetry & Analytics")
                print("=======================================================\n")

                frame_id = 0
                start_time = time.time()
                total_legs = len(self.route) - 1
                leg_duration_sec = 6.0  # Time to traverse each leg
                steps_per_leg = max(20, int(leg_duration_sec * self.fps))

                for leg_idx in range(total_legs):
                    p_start = self.route[leg_idx]
                    p_end = self.route[leg_idx + 1]

                    print(f"\n >>> Navigating Leg {leg_idx + 1}/{total_legs}: {p_start['name']} -> {p_end['name']}")

                    for step in range(steps_per_leg + 1):
                        loop_start = time.time()
                        alpha = step / steps_per_leg

                        # Smooth ease-in-out interpolation
                        smooth_alpha = 0.5 - 0.5 * math.cos(alpha * math.pi)
                        gt_pos = interpolate_points(p_start, p_end, smooth_alpha)

                        # Add slight natural roll/pitch/yaw
                        yaw_deg = math.degrees(math.atan2(p_end["y"] - p_start["y"], p_end["x"] - p_start["x"]))
                        elapsed_total = time.time() - start_time
                        roll_deg = round(math.sin(elapsed_total * 2.0) * 2.5, 2)
                        pitch_deg = round(math.cos(elapsed_total * 2.0) * 1.8, 2)

                        frame_id += 1
                        sim_time = round(time.time() - start_time, 3)

                        # 1. P2 Ground Truth Packet
                        gt_packet = {
                            "frame_id": frame_id,
                            "timestamp": sim_time,
                            "position": gt_pos,
                            "orientation": {
                                "roll": roll_deg,
                                "pitch": pitch_deg,
                                "yaw": round(yaw_deg, 2),
                            },
                            "lidar": {"bottom": round(gt_pos["z"] - 0.5, 2), "front": 18.5},
                        }

                        # 2. P3 Estimated Navigation Pose (with realistic small noise)
                        noise = 0.08
                        est_pos = {
                            "x": round(gt_pos["x"] + random.gauss(0, noise), 3),
                            "y": round(gt_pos["y"] + random.gauss(0, noise), 3),
                            "z": round(gt_pos["z"] + random.gauss(0, noise * 0.5), 3),
                            "roll": round(roll_deg + random.gauss(0, 0.2), 2),
                            "pitch": round(pitch_deg + random.gauss(0, 0.2), 2),
                            "yaw": round(yaw_deg + random.gauss(0, 0.4), 2),
                        }

                        p3_packet = {
                            "frame_id": frame_id,
                            "timestamp": sim_time,
                            "estimated_pose": est_pos,
                            "velocity": {"x": 3.5, "y": 1.2, "z": 0.0},
                            "tracking_state": "TRACKING_GOOD",
                            "confidence": round(random.uniform(0.94, 0.98), 2),
                            "processing_time_ms": round(random.uniform(12.0, 18.0), 1),
                        }

                        # Post to backend ingestion endpoints
                        try:
                            await client.post(f"{self.target_url}/api/v1/simulation/ground-truth", json=gt_packet)
                            await client.post(f"{self.target_url}/api/v1/navigation/state", json=p3_packet)

                            # Print metrics every 10 frames
                            if frame_id % 10 == 0:
                                dx = est_pos["x"] - gt_pos["x"]
                                dy = est_pos["y"] - gt_pos["y"]
                                dz = est_pos["z"] - gt_pos["z"]
                                err3d = math.sqrt(dx * dx + dy * dy + dz * dz)
                                print(
                                    f" [Frame #{frame_id:03d} | t={sim_time:05.1f}s] "
                                    f"GT=({gt_pos['x']:5.1f}, {gt_pos['y']:5.1f}, {gt_pos['z']:4.1f}) | "
                                    f"EST=({est_pos['x']:5.1f}, {est_pos['y']:5.1f}, {est_pos['z']:4.1f}) | "
                                    f"Loc Error: {err3d:.2f}m | Target: {p_end['name']}"
                                )
                        except Exception as exc:
                            print(f" [!] Ingestion error: {exc}")

                        sleep_dur = max(0.0, self.interval - (time.time() - loop_start))
                        await asyncio.sleep(sleep_dur)

                    print(f" [OK] Reached {p_end['name']}!")

                # Fetch final evaluation metrics
                print("\n=======================================================")
                print(" [M4 DEMO] Step 4: Final Navigation Analytics Summary")
                print("=======================================================")
                analytics_res = await client.get(f"{self.target_url}/api/v1/analytics/current")
                if analytics_res.status_code == 200:
                    m = analytics_res.json()
                    print(f" [+] Total Synchronized Samples : {m.get('sample_count')}")
                    print(f" [+] Final 3D Localization Error: {m['localization_error']['current']:.3f} m")
                    print(f" [+] Mean ATE                   : {m['ate']['mean']:.3f} m")
                    print(f" [+] RMSE ATE                   : {m['ate']['rmse']:.3f} m")
                    print(f" [+] Maximum Error              : {m['localization_error']['maximum']:.3f} m")
                    print(f" [+] Translational RPE RMSE     : {m['rpe']['rmse']:.3f} m")
                    print(f" [+] Accumulated Drift          : {m['drift']['percentage']:.2f}% ({m['drift']['absolute_meters']:.2f}m / {m['drift']['traveled_distance_m']:.1f}m traveled)")
                    print(f" [+] Sync Health Status         : {m['synchronization_status']}")
                print("=======================================================\n")

                if keep_alive_sec > 0:
                    print(f" [i] Keeping live streams active for {keep_alive_sec:.1f}s for dashboard observation...")
                    await asyncio.sleep(keep_alive_sec)
        finally:
            if cam_task and not cam_task.done():
                cam_task.cancel()
            if p1_task and not p1_task.done():
                p1_task.cancel()


def main():
    parser = argparse.ArgumentParser(description="SIH-NAVIS M4 Demonstration Runner")
    parser.add_argument("--target", default="http://localhost:8000", help="P4 Backend Target URL")
    parser.add_argument("--fps", type=float, default=15.0, help="Simulation telemetry rate (Hz)")
    parser.add_argument("--no-camera", action="store_true", help="Disable synthetic camera stream")
    parser.add_argument("--no-p1", action="store_true", help="Disable synthetic P1 perception stream")
    parser.add_argument("--keep-alive", type=float, default=5.0, help="Seconds to keep streams active after completion")
    args = parser.parse_args()

    runner = M4MissionDemoRunner(target_url=args.target, fps=args.fps)
    try:
        asyncio.run(
            runner.run_flight_simulation(
                enable_camera=not args.no_camera,
                enable_p1=not args.no_p1,
                keep_alive_sec=args.keep_alive,
            )
        )
    except KeyboardInterrupt:
        print("\n [!] Demo stopped by user.")


if __name__ == "__main__":
    main()
