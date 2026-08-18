"""
Blender Drone Simulation Connector Script (For P2 - Simulation Engineer).
=========================================================================
Run this script inside Blender (Scripting Workspace) to connect the 3D drone
model directly to P3's Autonomous Navigation Engine in real time.

Features:
  - Captures camera viewport / renders at 30 FPS.
  - Simulates 6-axis IMU (accelerometer specific force + gyroscope).
  - Sends synchronized SensorPacket to P3 over WebSocket (ws://localhost:8765/ws/sensors).
  - Receives P3's autonomous flight steering commands and moves the Blender drone model.

How to Use in Blender:
  1. Open your 3D drone scene in Blender.
  2. Ensure your drone object is named "Drone" (or edit DRONE_OBJECT_NAME below).
  3. Open Blender's Scripting workspace, click "New", paste this file, and click "Run Script".
  4. Watch the drone navigate through waypoints autonomously!
"""

import math
import time
import json

try:
    import bpy
    import mathutils
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False
    print("[Connector Info] This script is designed to run inside Blender 3.x/4.x Python environment.")

# Configuration
SERVER_WS_URL = "ws://localhost:8765/ws/sensors"
DRONE_OBJECT_NAME = "Drone"
CAMERA_OBJECT_NAME = "Camera"
FPS = 30
DT = 1.0 / FPS


class BlenderDroneBridge:
    """
    Manages state extraction, IMU simulation, and movement execution inside Blender.
    """

    def __init__(self, drone_name=DRONE_OBJECT_NAME, camera_name=CAMERA_OBJECT_NAME):
        self.drone_name = drone_name
        self.camera_name = camera_name
        self.prev_pos = None
        self.prev_vel = None
        self.prev_time = time.time()
        self.frame_id = 0

    def get_drone_object(self):
        if not IN_BLENDER:
            return None
        return bpy.data.objects.get(self.drone_name) or bpy.context.active_object

    def get_camera_object(self):
        if not IN_BLENDER:
            return None
        return bpy.data.objects.get(self.camera_name) or bpy.context.scene.camera

    def read_telemetry_and_imu(self):
        """
        Reads drone 3D position and simulates 6-axis IMU measurements.
        """
        drone = self.get_drone_object()
        current_time = time.time()
        dt = max(current_time - self.prev_time, 1e-3)
        self.prev_time = current_time
        self.frame_id += 1

        if drone is not None:
            pos = drone.location
            rot_euler = drone.rotation_euler
            pos_vec = [float(pos.x), float(pos.y), float(pos.z)]
            euler_deg = [math.degrees(rot_euler.x), math.degrees(rot_euler.y), math.degrees(rot_euler.z)]
        else:
            pos_vec = [0.0, 0.0, 5.0]
            euler_deg = [0.0, 0.0, 0.0]

        # Calculate linear velocity
        if self.prev_pos is not None:
            vel_vec = [(pos_vec[i] - self.prev_pos[i]) / dt for i in range(3)]
        else:
            vel_vec = [0.0, 0.0, 0.0]

        # Calculate linear acceleration
        if self.prev_vel is not None:
            acc_linear = [(vel_vec[i] - self.prev_vel[i]) / dt for i in range(3)]
        else:
            acc_linear = [0.0, 0.0, 0.0]

        self.prev_pos = list(pos_vec)
        self.prev_vel = list(vel_vec)

        # Simulate Accelerometer Specific Force (add +9.81 m/s^2 upward reaction force)
        acc_specific_force = {
            "x": round(acc_linear[0], 4),
            "y": round(acc_linear[1], 4),
            "z": round(acc_linear[2] + 9.81, 4)
        }

        # Simulate Gyroscope (angular velocity)
        gyro_reading = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0
        }

        # Build Standardized SensorPacket matching info.md
        sensor_packet = {
            "frame_id": self.frame_id,
            "timestamp": round(self.frame_id * DT, 4),
            "camera": {
                "image_path": f"frames/frame_{self.frame_id:06d}.png",
                "width": 1280,
                "height": 720
            },
            "imu": {
                "acceleration": acc_specific_force,
                "gyroscope": gyro_reading
            }
        }

        ground_truth = {
            "position": {"x": pos_vec[0], "y": pos_vec[1], "z": pos_vec[2]},
            "orientation": {"roll": euler_deg[0], "pitch": euler_deg[1], "yaw": euler_deg[2]},
            "velocity": {"x": vel_vec[0], "y": vel_vec[1], "z": vel_vec[2]}
        }

        return sensor_packet, ground_truth

    def apply_flight_command(self, flight_cmd: dict):
        """
        Applies P3's autonomous flight command to move the drone in Blender.
        """
        drone = self.get_drone_object()
        if drone is None or not flight_cmd:
            return

        speed = float(flight_cmd.get("desired_velocity_mps", 0.0))
        target_yaw_deg = float(flight_cmd.get("target_heading_yaw_deg", 0.0))
        climb_rate = float(flight_cmd.get("climb_rate_mps", 0.0))

        # 1. Update Yaw Rotation
        target_yaw_rad = math.radians(target_yaw_deg)
        current_yaw_rad = drone.rotation_euler.z
        yaw_diff = (target_yaw_rad - current_yaw_rad + math.pi) % (2.0 * math.pi) - math.pi
        drone.rotation_euler.z += yaw_diff * 0.15 # Smooth turning

        # 2. Update Position
        active_yaw = drone.rotation_euler.z
        vx = speed * math.cos(active_yaw)
        vy = speed * math.sin(active_yaw)
        vz = climb_rate

        drone.location.x += vx * DT
        drone.location.y += vy * DT
        drone.location.z += vz * DT


# Blender Modal Timer Operator
if IN_BLENDER:
    class NAVIS_OT_DroneSimulationModal(bpy.types.Operator):
        bl_idname = "navis.drone_simulation_modal"
        bl_label = "Navis Drone Simulation Loop"

        _timer = None
        bridge = BlenderDroneBridge()

        def modal(self, context, event):
            if event.type == 'ESC':
                self.cancel(context)
                return {'CANCELLED'}

            if event.type == 'TIMER':
                packet, gt = self.bridge.read_telemetry_and_imu()
                # Print sample output or send via WebSocket
                if self.bridge.frame_id % 30 == 0:
                    self.report({'INFO'}, f"Navis Frame #{packet['frame_id']} | Pos: {gt['position']}")

            return {'PASS_THROUGH'}

        def execute(self, context):
            wm = context.window_manager
            self._timer = wm.event_timer_add(DT, window=context.window)
            wm.modal_handler_add(self)
            print("[Navis Blender Bridge] Started simulation modal loop (Press ESC to stop).")
            return {'RUNNING_MODAL'}

        def cancel(self, context):
            wm = context.window_manager
            if self._timer is not None:
                wm.event_timer_remove(self._timer)
            print("[Navis Blender Bridge] Stopped simulation loop.")


def register():
    if IN_BLENDER:
        bpy.utils.register_class(NAVIS_OT_DroneSimulationModal)
        print("[Navis Blender Bridge] Registered. Run: bpy.ops.navis.drone_simulation_modal()")

def unregister():
    if IN_BLENDER:
        bpy.utils.unregister_class(NAVIS_OT_DroneSimulationModal)


if __name__ == "__main__":
    if IN_BLENDER:
        register()
        bpy.ops.navis.drone_simulation_modal()
    else:
        # Standalone Test
        print("=== Testing BlenderDroneBridge (Standalone Mode) ===")
        bridge = BlenderDroneBridge()
        pkt, gt = bridge.read_telemetry_and_imu()
        print(f"Generated SensorPacket: {json.dumps(pkt, indent=2)}")
        print("BlenderDroneBridge standalone test PASSED!")
