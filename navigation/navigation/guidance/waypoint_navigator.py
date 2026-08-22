"""
Waypoint Guidance & Autonomous Flight Controller Module (P3 Module).
====================================================================
Computes smooth 3D flight trajectory commands to guide the drone between waypoints:
  - Ingests mission waypoints (from JSON files or dynamic dashboard API).
  - Calculates line-of-sight bearing, Cross-Track Error (CTE), and climb rates.
  - Smooth acceleration/braking velocity profiling to prevent jerky overshoot.
  - Generates autonomous flight commands sent back to Blender (P2).
"""

from typing import Dict, List, Optional, Tuple, Any, Union
import os
import json
import numpy as np


class Waypoint:
    """Represents a 3D mission waypoint."""

    def __init__(
        self,
        wp_id: int,
        x: float,
        y: float,
        z: float,
        name: str = "",
        speed_mps: float = 3.0,
        acceptance_radius_m: float = 0.6,
        hold_time_s: float = 0.0
    ):
        self.id = int(wp_id)
        self.name = name or f"Waypoint_{wp_id}"
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.speed_mps = float(speed_mps)
        self.acceptance_radius_m = float(acceptance_radius_m)
        self.hold_time_s = float(hold_time_s)

    @property
    def position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "speed_mps": self.speed_mps,
            "acceptance_radius_m": self.acceptance_radius_m,
            "hold_time_s": self.hold_time_s
        }


class WaypointNavigator:
    """
    Autonomous Waypoint Guidance & Steering Controller.
    """

    def __init__(
        self,
        waypoints: Optional[List[Union[Dict[str, Any], Waypoint]]] = None,
        default_cruise_speed: float = 3.0,
        default_acceptance_radius: float = 0.6,
        max_climb_rate: float = 1.5,
        max_yaw_rate: float = 45.0
    ):
        self.default_cruise_speed = float(default_cruise_speed)
        self.default_acceptance_radius = float(default_acceptance_radius)
        self.max_climb_rate = float(max_climb_rate)
        self.max_yaw_rate = float(max_yaw_rate)

        self.waypoints: List[Waypoint] = []
        self.current_wp_idx: int = 0
        self.previous_wp_pos: Optional[np.ndarray] = None
        self.is_mission_active: bool = False

        if waypoints:
            self.set_waypoints(waypoints)

    def load_waypoints_from_file(self, filepath: str) -> bool:
        """Loads waypoints from a JSON file."""
        if not os.path.exists(filepath):
            return False
        with open(filepath, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            self.set_waypoints(data)
            return True
        elif isinstance(data, dict) and "waypoints" in data:
            self.set_waypoints(data["waypoints"])
            return True
        return False

    def set_waypoints(self, waypoint_list: List[Union[Dict[str, Any], Waypoint]]):
        """Sets the active mission waypoint list."""
        self.waypoints = []
        for i, item in enumerate(waypoint_list):
            if isinstance(item, Waypoint):
                self.waypoints.append(item)
            elif isinstance(item, dict):
                wp = Waypoint(
                    wp_id=item.get("id", i + 1),
                    name=item.get("name", f"WP_{i + 1}"),
                    x=float(item.get("x", 0.0)),
                    y=float(item.get("y", 0.0)),
                    z=float(item.get("z", 5.0)),
                    speed_mps=float(item.get("speed_mps", item.get("speed", self.default_cruise_speed))),
                    acceptance_radius_m=float(item.get("acceptance_radius_m", item.get("acceptance_radius", self.default_acceptance_radius))),
                    hold_time_s=float(item.get("hold_time_s", 0.0))
                )
                self.waypoints.append(wp)

        self.current_wp_idx = 0
        self.previous_wp_pos = None
        self.is_mission_active = len(self.waypoints) > 0
        self._world_origin_set = False

    def anchor_to_world_origin(self, origin: np.ndarray):
        """Anchors relative waypoint offsets to initial 3D spawn world coordinates."""
        if getattr(self, "_world_origin_set", False):
            return
        origin = np.array(origin, dtype=np.float64)
        for wp in self.waypoints:
            wp.x += origin[0]
            wp.y += origin[1]
            wp.z += origin[2]
        self._world_origin_set = True

    def get_active_waypoint(self) -> Optional[Waypoint]:
        """Returns the current active target waypoint."""
        if not self.is_mission_active or self.current_wp_idx >= len(self.waypoints):
            return None
        return self.waypoints[self.current_wp_idx]

    def compute_flight_command(
        self,
        current_pos: np.ndarray,
        current_yaw_deg: float,
        dt: float = 0.033
    ) -> Dict[str, Any]:
        """
        Computes steering and velocity control commands to reach the target waypoint.

        Args:
            current_pos: Estimated 3D drone position [x, y, z] in meters.
            current_yaw_deg: Current estimated heading in degrees [0 to 360 or -180 to 180].
            dt: Frame time delta (seconds).

        Returns:
            Flight command dictionary sent to Blender / Simulator.
        """
        current_pos = np.array(current_pos, dtype=np.float64)

        if not self.is_mission_active or not self.waypoints:
            return {
                "active_waypoint_idx": None,
                "active_waypoint_name": "None",
                "distance_to_waypoint_m": 0.0,
                "cross_track_error_m": 0.0,
                "desired_velocity_mps": 0.0,
                "target_heading_yaw_deg": current_yaw_deg,
                "commanded_yaw_rate_dps": 0.0,
                "climb_rate_mps": 0.0,
                "mission_status": "NO_MISSION"
            }

        if self.current_wp_idx >= len(self.waypoints):
            return {
                "active_waypoint_idx": len(self.waypoints),
                "active_waypoint_name": "Completed",
                "distance_to_waypoint_m": 0.0,
                "cross_track_error_m": 0.0,
                "desired_velocity_mps": 0.0,
                "target_heading_yaw_deg": current_yaw_deg,
                "commanded_yaw_rate_dps": 0.0,
                "climb_rate_mps": 0.0,
                "mission_status": "MISSION_COMPLETED"
            }

        target_wp = self.waypoints[self.current_wp_idx]
        target_pos = target_wp.position

        # 1. 3D Displacement Vector & Distance
        disp = target_pos - current_pos
        dist_3d = float(np.linalg.norm(disp))
        dist_xy = float(np.linalg.norm(disp[:2]))
        dist_z = float(disp[2])

        mission_status = "NAVIGATING"

        # 2. Check Acceptance Radius (Arrival condition)
        if dist_3d <= target_wp.acceptance_radius_m:
            self.previous_wp_pos = target_pos.copy()
            self.current_wp_idx += 1

            if self.current_wp_idx >= len(self.waypoints):
                return {
                    "active_waypoint_idx": len(self.waypoints),
                    "active_waypoint_name": "Mission Goal",
                    "distance_to_waypoint_m": 0.0,
                    "cross_track_error_m": 0.0,
                    "desired_velocity_mps": 0.0,
                    "target_heading_yaw_deg": current_yaw_deg,
                    "commanded_yaw_rate_dps": 0.0,
                    "climb_rate_mps": 0.0,
                    "mission_status": "MISSION_COMPLETED"
                }
            else:
                mission_status = "WAYPOINT_REACHED"
                target_wp = self.waypoints[self.current_wp_idx]
                target_pos = target_wp.position
                disp = target_pos - current_pos
                dist_3d = float(np.linalg.norm(disp))
                dist_xy = float(np.linalg.norm(disp[:2]))
                dist_z = float(disp[2])

        # 3. Target Heading Yaw (Line-of-Sight Bearing)
        if dist_xy > 0.1:
            target_yaw_rad = np.arctan2(disp[1], disp[0])
            target_yaw_deg = float(np.degrees(target_yaw_rad))
        else:
            target_yaw_deg = current_yaw_deg

        # Yaw error wrapped to [-180, 180]
        yaw_err = (target_yaw_deg - current_yaw_deg + 180.0) % 360.0 - 180.0
        # Proportional yaw turn rate with deadband to prevent hunting
        if abs(yaw_err) < 2.5:
            yaw_rate_cmd = 0.0
            target_yaw_deg = current_yaw_deg
        else:
            k_yaw = 1.8
            yaw_rate_cmd = float(np.clip(k_yaw * yaw_err, -self.max_yaw_rate, self.max_yaw_rate))

        # 4. Smooth Velocity Profiling (Acceleration & Braking)
        cruise_speed = target_wp.speed_mps
        if dist_xy < 2.0:
            # Smoothly ramp down speed when arriving at waypoint
            desired_speed = float(np.clip(cruise_speed * (dist_xy / 2.0), 0.4, cruise_speed))
        else:
            desired_speed = cruise_speed

        # 5. Climb Rate (Vertical Z Control)
        k_z = 1.0
        climb_rate_cmd = float(np.clip(k_z * dist_z, -self.max_climb_rate, self.max_climb_rate))

        # 6. Aerodynamic 3D Attitude Calculation (Banked Coordinated Turns & Forward Pitch)
        # Centripetal acceleration formula for banked turn: tan(phi) = - v * yaw_rate / g
        yaw_rate_rad = np.radians(yaw_rate_cmd)
        centripetal_acc = desired_speed * yaw_rate_rad
        target_roll_rad = -np.arctan2(centripetal_acc, 9.81)
        target_roll_deg = float(np.clip(np.degrees(target_roll_rad), -30.0, 30.0))

        # Forward cruise pitch tilt (nose-down during forward flight, nose-up flare when braking)
        if dist_xy < 1.0:
            target_pitch_deg = 3.0  # Slight nose-up brake when approaching waypoint
        else:
            target_pitch_deg = float(np.clip(-2.5 * desired_speed, -22.0, 5.0))

        # 7. Cross-Track Error (CTE) Calculation
        cte = 0.0
        if self.previous_wp_pos is not None:
            p_a = self.previous_wp_pos[:2]
            p_b = target_pos[:2]
            p_curr = current_pos[:2]
            seg = p_b - p_a
            seg_len = np.linalg.norm(seg)
            if seg_len > 0.5:
                # Perpendicular distance formula: |(p_curr - p_a) x (p_b - p_a)| / |p_b - p_a|
                cross_prod = (p_curr[0] - p_a[0]) * (p_b[1] - p_a[1]) - (p_curr[1] - p_a[1]) * (p_b[0] - p_a[0])
                cte = float(cross_prod / seg_len)

        return {
            "type": "waypoint",
            "active_waypoint_idx": self.current_wp_idx + 1,
            "active_waypoint_name": target_wp.name,
            "target_x": round(float(target_pos[0]), 4),
            "target_y": round(float(target_pos[1]), 4),
            "target_z": round(float(target_pos[2]), 4),
            "distance_to_waypoint_m": round(dist_3d, 3),
            "cross_track_error_m": round(cte, 3),
            "desired_velocity_mps": round(desired_speed, 2),
            "target_heading_yaw_deg": round(target_yaw_deg, 2),
            "target_roll_deg": round(target_roll_deg, 2),
            "target_pitch_deg": round(target_pitch_deg, 2),
            "commanded_yaw_rate_dps": round(yaw_rate_cmd, 2),
            "climb_rate_mps": round(climb_rate_cmd, 2),
            "mission_status": mission_status
        }

    def reset(self):
        """Resets mission to the starting waypoint."""
        self.current_wp_idx = 0
        self.previous_wp_pos = None


if __name__ == "__main__":
    print("=== Testing WaypointNavigator ===")
    nav = WaypointNavigator([
        {"id": 1, "name": "Takeoff", "x": 0.0, "y": 0.0, "z": 5.0, "speed": 2.0},
        {"id": 2, "name": "Waypoint_B", "x": 10.0, "y": 0.0, "z": 5.0, "speed": 3.0},
        {"id": 3, "name": "Waypoint_C", "x": 10.0, "y": 10.0, "z": 6.0, "speed": 3.0}
    ])

    cmd1 = nav.compute_flight_command(current_pos=np.array([0.0, 0.0, 0.0]), current_yaw_deg=0.0)
    print(f"Takeoff Command: {cmd1}")
    assert cmd1["climb_rate_mps"] > 0.0

    # Drone reaches WP 1
    cmd2 = nav.compute_flight_command(current_pos=np.array([0.0, 0.0, 4.9]), current_yaw_deg=0.0)
    print(f"Reached WP 1 -> Switching to WP 2: {cmd2['mission_status']}")
    assert cmd2["active_waypoint_idx"] == 2

    print("WaypointNavigator test PASSED!")
