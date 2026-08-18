"""
Unit Tests for Waypoint Guidance & Steering Controller (waypoint_navigator.py).
"""

import unittest
import numpy as np

from navigation.guidance.waypoint_navigator import WaypointNavigator, Waypoint
from navigation.engine import NavigationEngine


class TestGuidance(unittest.TestCase):

    def setUp(self):
        self.sample_wps = [
            {"id": 1, "name": "WP_1", "x": 0.0, "y": 0.0, "z": 5.0, "speed": 2.0, "acceptance_radius_m": 0.5},
            {"id": 2, "name": "WP_2", "x": 10.0, "y": 0.0, "z": 5.0, "speed": 3.0, "acceptance_radius_m": 0.5},
            {"id": 3, "name": "WP_3", "x": 10.0, "y": 10.0, "z": 5.0, "speed": 3.0, "acceptance_radius_m": 0.5}
        ]
        self.navigator = WaypointNavigator(self.sample_wps)

    def test_waypoint_initialization(self):
        self.assertEqual(len(self.navigator.waypoints), 3)
        self.assertTrue(self.navigator.is_mission_active)
        active_wp = self.navigator.get_active_waypoint()
        self.assertIsNotNone(active_wp)
        self.assertEqual(active_wp.id, 1)

    def test_takeoff_climb_command(self):
        # Drone at ground (0, 0, 0), WP1 at (0, 0, 5)
        cmd = self.navigator.compute_flight_command(current_pos=np.array([0.0, 0.0, 0.0]), current_yaw_deg=0.0)
        self.assertGreater(cmd["climb_rate_mps"], 0.5)
        self.assertEqual(cmd["mission_status"], "NAVIGATING")

    def test_waypoint_transition(self):
        # Drone reaches WP1 (within 0.3m < 0.5m acceptance)
        cmd = self.navigator.compute_flight_command(current_pos=np.array([0.0, 0.0, 4.8]), current_yaw_deg=0.0)
        self.assertEqual(cmd["mission_status"], "WAYPOINT_REACHED")
        self.assertEqual(cmd["active_waypoint_idx"], 2) # Target switched to WP2

    def test_cross_track_error(self):
        # Reach WP1 first to establish line WP1 -> WP2 (along X axis from (0,0) to (10,0))
        self.navigator.compute_flight_command(current_pos=np.array([0.0, 0.0, 5.0]), current_yaw_deg=0.0)

        # Drone at (5.0, 2.0, 5.0) -> 2.0m lateral offset along Y axis
        cmd = self.navigator.compute_flight_command(current_pos=np.array([5.0, 2.0, 5.0]), current_yaw_deg=0.0)
        self.assertAlmostEqual(abs(cmd["cross_track_error_m"]), 2.0, places=1)

    def test_mission_completion(self):
        # Simulate reaching WP1, WP2, WP3
        self.navigator.compute_flight_command(np.array([0.0, 0.0, 5.0]), 0.0)  # reach 1
        self.navigator.compute_flight_command(np.array([10.0, 0.0, 5.0]), 0.0) # reach 2
        cmd_final = self.navigator.compute_flight_command(np.array([10.0, 10.0, 5.0]), 0.0) # reach 3

        self.assertEqual(cmd_final["mission_status"], "MISSION_COMPLETED")
        self.assertAlmostEqual(cmd_final["desired_velocity_mps"], 0.0)

    def test_engine_guidance_integration(self):
        engine = NavigationEngine(waypoints=self.sample_wps)
        packet = {
            "frame_id": 1,
            "timestamp": 0.033,
            "camera": {"frame": np.zeros((720, 1280, 3), dtype=np.uint8)},
            "imu": {"acceleration": [0, 0, 9.81], "gyroscope": [0, 0, 0]}
        }
        res = engine.process_packet(packet)
        self.assertIn("flight_command", res)
        cmd = res["flight_command"]
        self.assertIn("desired_velocity_mps", cmd)
        self.assertIn("target_heading_yaw_deg", cmd)
        self.assertIn("mission_status", cmd)


if __name__ == "__main__":
    unittest.main()
