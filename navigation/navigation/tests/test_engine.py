"""
Unit Tests for Top-Level Navigation Engine (engine.py).
"""

import unittest
import numpy as np

from navigation.engine import NavigationEngine
from navigation.utils.mock_generator import MockDataGenerator


class TestNavigationEngine(unittest.TestCase):

    def test_process_packet_schema(self):
        engine = NavigationEngine(init_pos=np.array([0.0, 0.0, 5.0]))

        # Create sample packet matching info.md
        dummy_frame = np.full((720, 1280, 3), 120, dtype=np.uint8)
        packet = {
            "frame_id": 1,
            "timestamp": 0.033,
            "camera": {
                "frame": dummy_frame,
                "width": 1280,
                "height": 720
            },
            "imu": {
                "acceleration": {"x": 0.0, "y": 0.0, "z": 9.81},
                "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.0}
            }
        }

        output = engine.process_packet(packet)

        # Check required fields from info.md
        self.assertEqual(output["frame_id"], 1)
        self.assertEqual(output["timestamp"], 0.033)
        self.assertIn("estimated_pose", output)
        self.assertIn("velocity", output)
        self.assertIn("tracking_state", output)
        self.assertIn("confidence", output)

        pose = output["estimated_pose"]
        self.assertIn("x", pose)
        self.assertIn("y", pose)
        self.assertIn("z", pose)
        self.assertIn("roll", pose)
        self.assertIn("pitch", pose)
        self.assertIn("yaw", pose)

        vel = output["velocity"]
        self.assertIn("x", vel)
        self.assertIn("y", vel)
        self.assertIn("z", vel)

    def test_engine_streaming_trajectory(self):
        engine = NavigationEngine()
        gen = MockDataGenerator(trajectory_type="circular", duration=1.0, camera_hz=30)

        outputs = []
        fid = 1

        for sensor_type, packet in gen.stream_dataset():
            if sensor_type == "camera":
                gt = packet["ground_truth"]
                sensor_packet = {
                    "frame_id": fid,
                    "timestamp": packet["timestamp"],
                    "camera": {
                        "frame": packet["frame"],
                        "width": 1280,
                        "height": 720
                    },
                    "imu": {
                        "acceleration": {
                            "x": float(gt["acceleration"][0]),
                            "y": float(gt["acceleration"][1]),
                            "z": float(gt["acceleration"][2] + 9.81)
                        },
                        "gyroscope": {
                            "x": float(gt["angular_velocity"][0]),
                            "y": float(gt["angular_velocity"][1]),
                            "z": float(gt["angular_velocity"][2])
                        }
                    }
                }
                out = engine.process_packet(sensor_packet)
                outputs.append(out)
                fid += 1

        self.assertGreaterEqual(len(outputs), 30)
        self.assertEqual(outputs[-1]["frame_id"], len(outputs))
        self.assertGreater(outputs[-1]["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
