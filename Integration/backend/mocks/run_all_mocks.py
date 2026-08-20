"""Mock Producers Orchestrator.

Launches all four mock producers (P1 Perception, P2 Simulation Ground Truth,
P3 Navigation, and Camera Binary Stream) concurrently for independent integration testing.
"""

import argparse
import asyncio
import sys

from mocks.mock_camera import MockCameraProducer
from mocks.mock_p1 import MockP1Producer
from mocks.mock_p2 import MockP2Producer
from mocks.mock_p3 import MockP3Producer


async def run_producers(
    target_http: str,
    target_ws: str,
    p1_fps: float,
    p2_fps: float,
    p3_fps: float,
    cam_fps: float,
    frames: int,
    no_cam: bool,
):
    print("=" * 65)
    print("  SIH-NAVIS M3 Multi-Producer Simulation Suite")
    print("=" * 65)
    print(f"  Target Backend HTTP: {target_http}")
    print(f"  Target Camera WS:    {target_ws}")
    print(f"  P1 Perception:       {p1_fps} Hz")
    print(f"  P2 Ground Truth:     {p2_fps} Hz")
    print(f"  P3 Navigation:       {p3_fps} Hz")
    print(f"  Camera Video:        {cam_fps if not no_cam else 'Disabled'} FPS")
    print(f"  Frame Limit:         {'Infinite' if frames == 0 else frames}")
    print("=" * 65)

    p1 = MockP1Producer(target_url=target_http, fps=p1_fps, total_frames=frames)
    p2 = MockP2Producer(target_url=target_http, fps=p2_fps, total_frames=frames)
    p3 = MockP3Producer(target_url=target_http, fps=p3_fps, total_frames=frames)

    tasks = [
        asyncio.create_task(p1.run()),
        asyncio.create_task(p2.run()),
        asyncio.create_task(p3.run()),
    ]

    if not no_cam:
        cam = MockCameraProducer(ws_url=target_ws, fps=cam_fps, total_frames=frames)
        tasks.append(asyncio.create_task(cam.run()))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\nStopping all mock producers...")
        for t in tasks:
            t.cancel()


def main():
    parser = argparse.ArgumentParser(description="Run all SIH-NAVIS mock data producers")
    parser.add_argument("--http", default="http://localhost:8000", help="P4 Backend HTTP URL")
    parser.add_argument("--ws", default="ws://localhost:8000/ws/camera?role=producer", help="Camera WebSocket URL")
    parser.add_argument("--p1-fps", type=float, default=5.0, help="P1 Perception FPS")
    parser.add_argument("--p2-fps", type=float, default=20.0, help="P2 Simulation FPS")
    parser.add_argument("--p3-fps", type=float, default=20.0, help="P3 Navigation FPS")
    parser.add_argument("--cam-fps", type=float, default=15.0, help="Camera FPS")
    parser.add_argument("--frames", type=int, default=0, help="Total frames (0 for infinite)")
    parser.add_argument("--no-camera", action="store_true", help="Disable camera producer")
    args = parser.parse_args()

    try:
        asyncio.run(
            run_producers(
                target_http=args.http,
                target_ws=args.ws,
                p1_fps=args.p1_fps,
                p2_fps=args.p2_fps,
                p3_fps=args.p3_fps,
                cam_fps=args.cam_fps,
                frames=args.frames,
                no_cam=args.no_camera,
            )
        )
    except KeyboardInterrupt:
        print("\nExited.")
        sys.exit(0)


if __name__ == "__main__":
    main()
