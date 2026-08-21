"""End-to-end M4 flight demonstration verification test."""

import asyncio
import json
import threading
import pytest
import uvicorn
import websockets
from app.main import app
from mocks.run_m4_demo import M4MissionDemoRunner


def test_full_m4_e2e_pipeline():
    """Verify that a live WebSocket client receives changing telemetry, analytics, camera, and mission progression."""
    async def _run_test():
        port = 8899
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        await asyncio.sleep(1.0)

        received_frames = []
        received_analytics = []
        received_missions = []
        received_camera_bytes = 0

        # Connect Telemetry and Camera WebSockets simultaneously
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws/telemetry") as tel_ws:
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/camera?role=viewer") as cam_ws:

                async def listen_telemetry():
                    while True:
                        try:
                            msg_txt = await asyncio.wait_for(tel_ws.recv(), timeout=40.0)
                            msg = json.loads(msg_txt)
                            evt = msg.get("event")
                            if evt == "navigation":
                                received_frames.append(msg["data"]["frame_id"])
                            elif evt == "analytics":
                                received_analytics.append(msg["data"])
                            elif evt in ("mission_status", "mission_progress"):
                                received_missions.append(msg)
                        except asyncio.CancelledError:
                            break
                        except Exception:
                            break

                async def listen_camera():
                    nonlocal received_camera_bytes
                    while True:
                        try:
                            cam_data = await asyncio.wait_for(cam_ws.recv(), timeout=40.0)
                            if isinstance(cam_data, bytes):
                                received_camera_bytes += len(cam_data)
                        except asyncio.CancelledError:
                            break
                        except Exception:
                            break

                task1 = asyncio.create_task(listen_telemetry())
                task2 = asyncio.create_task(listen_camera())

                # Run demo simulation at 30 fps for test execution
                runner = M4MissionDemoRunner(target_url=f"http://127.0.0.1:{port}", fps=30.0)
                await runner.run_flight_simulation(enable_camera=True, enable_p1=True, keep_alive_sec=0.5)

                await asyncio.sleep(0.5)
                task1.cancel()
                task2.cancel()

        # Assertions on received data stream
        assert len(received_frames) > 100, f"Expected >100 frames, got {len(received_frames)}"
        assert received_frames[0] < received_frames[-1], "Frame IDs should increase monotonically"
        assert len(received_analytics) > 100, f"Expected >100 analytics, got {len(received_analytics)}"
        assert len(received_missions) >= 4, f"Expected >=4 mission lifecycle events, got {len(received_missions)}"
        assert received_camera_bytes > 30000, f"Expected binary camera frames, got {received_camera_bytes} bytes"

        final_analytics = received_analytics[-1]
        assert final_analytics["localization_error"]["current"] is not None
        assert final_analytics["ate"]["rmse"] is not None
        assert final_analytics["synchronization_status"] in ("SYNCED", "PARTIAL")

    asyncio.run(_run_test())
