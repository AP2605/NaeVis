"""
Blender Drone Simulation Connector Script (For P2 - Simulation Engineer).
=========================================================================
Run this script inside Blender (Scripting Workspace) to connect the 3D drone
model directly to P3's Autonomous Navigation Engine in real time.

Features:
  - Prints all scene objects to Blender System Console for easy debugging.
  - Automatically identifies the Drone Mesh / Root object.
  - Captures 3D world telemetry & simulates 6-axis IMU (accel + gyro).
  - Streams SensorPacket to P3 over WebSocket / HTTP.
  - Smoothly rotates and moves the 3D Drone along mission waypoints.
  - Forces 3D Viewport live redraws & dependency graph updates.

How to Use in Blender:
  1. In Blender 3D Viewport, click/select your drone model (or set DRONE_OBJECT_NAME).
  2. Set SERVER_IP to P3's IP (e.g. "10.247.227.32" or "localhost").
  3. In Blender Scripting tab, open this file, and click "Run Script" (or press Alt+P).
  4. Press ESC in the 3D Viewport to stop.
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
    print("[Connector Info] Running outside Blender (Standalone Mode).")

try:
    import websocket
    HAS_WEBSOCKET_CLIENT = True
except ImportError:
    HAS_WEBSOCKET_CLIENT = False
    import urllib.request

# =========================================================================
# CONFIGURATION — Set P3's IP & Drone Object Name
# =========================================================================
SERVER_IP = "10.247.227.32"          # <--- P3 Server IP
SERVER_PORT = 8765
SERVER_WS_URL = f"ws://{SERVER_IP}:{SERVER_PORT}/ws/sensors"
SERVER_HTTP_URL = f"http://{SERVER_IP}:{SERVER_PORT}/api/packet"

# If your drone object has a specific name in Blender, put it here:
DRONE_OBJECT_NAME = ""               # Leave empty "" to auto-select active/first object
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
        self.ws = None
        self._drone_obj = None

    def connect_ws(self):
        """Attempts to open persistent WebSocket connection to P3 server."""
        if HAS_WEBSOCKET_CLIENT and self.ws is None:
            try:
                self.ws = websocket.create_connection(SERVER_WS_URL, timeout=2.0)
                print(f"[Blender Bridge] Connected to P3 WebSocket: {SERVER_WS_URL}")
            except Exception as e:
                self.ws = None

    def find_and_bind_drone(self):
        """Finds and locks onto the drone object in the scene."""
        if not IN_BLENDER:
            return None

        # 1. If explicit name provided and exists
        if self.drone_name and self.drone_name in bpy.data.objects:
            self._drone_obj = bpy.data.objects[self.drone_name]
            return self._drone_obj

        # 2. Check active object in 3D Viewport if not camera
        if bpy.context.active_object and bpy.context.active_object.type != 'CAMERA':
            self._drone_obj = bpy.context.active_object
            return self._drone_obj

        # 3. Search by common keywords (drone, quad, uav, body, aircraft, plane, mesh, root)
        candidates = []
        for o in bpy.data.objects:
            if o.type != 'CAMERA':
                candidates.append(o)
                if any(k in o.name.lower() for k in ["drone", "quad", "uav", "body", "frame", "aircraft", "plane"]):
                    self._drone_obj = o
                    return self._drone_obj

        # 4. Fallback to first non-camera object
        if candidates:
            self._drone_obj = candidates[0]
            return self._drone_obj

        return None

    def get_drone_object(self):
        if self._drone_obj is None or (IN_BLENDER and self._drone_obj.name not in bpy.data.objects):
            self.find_and_bind_drone()
        return self._drone_obj

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
            pos_vec = [0.0, 0.0, 0.0]
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

        # Simulate Accelerometer Specific Force (+9.81 m/s^2 reaction force)
        acc_specific_force = {
            "x": round(acc_linear[0], 4),
            "y": round(acc_linear[1], 4),
            "z": round(acc_linear[2] + 9.81, 4)
        }

        # Simulate Gyroscope
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
            },
            "sim_position": {
                "x": pos_vec[0],
                "y": pos_vec[1],
                "z": pos_vec[2]
            }
        }

        ground_truth = {
            "position": {"x": pos_vec[0], "y": pos_vec[1], "z": pos_vec[2]},
            "orientation": {"roll": euler_deg[0], "pitch": euler_deg[1], "yaw": euler_deg[2]},
            "velocity": {"x": vel_vec[0], "y": vel_vec[1], "z": vel_vec[2]}
        }

        return sensor_packet, ground_truth

    def send_sensor_packet(self, packet: dict) -> dict:
        """
        Sends sensor packet to P3 Navigation server and receives steering command.
        Uses WebSocket if available, with automatic HTTP fallback.
        """
        # 1. Try WebSocket
        if HAS_WEBSOCKET_CLIENT:
            if self.ws is None:
                self.connect_ws()
            if self.ws is not None:
                try:
                    self.ws.send(json.dumps(packet))
                    resp = json.loads(self.ws.recv())
                    return resp.get("flight_command", {})
                except Exception:
                    self.ws = None

        # 2. HTTP Fallback
        try:
            req = urllib.request.Request(
                SERVER_HTTP_URL,
                data=json.dumps(packet).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=0.5) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data.get("flight_command", {})
        except Exception:
            return {}

    def apply_flight_command(self, flight_cmd: dict):
        """
        Applies P3's autonomous flight command to physically move the drone in Blender.
        """
        drone = self.get_drone_object()
        if drone is None or not flight_cmd:
            return

        speed = float(flight_cmd.get("desired_velocity_mps", 2.0))
        target_yaw_deg = float(flight_cmd.get("target_heading_yaw_deg", 0.0))
        climb_rate = float(flight_cmd.get("climb_rate_mps", 0.5))

        # 1. Smooth Yaw Heading Rotation
        target_yaw_rad = math.radians(target_yaw_deg)
        current_yaw_rad = drone.rotation_euler.z
        yaw_diff = (target_yaw_rad - current_yaw_rad + math.pi) % (2.0 * math.pi) - math.pi
        drone.rotation_euler.z += yaw_diff * 0.20

        # 2. Forward Velocity Vector aligned with Target Heading
        active_yaw = drone.rotation_euler.z
        vx = speed * math.cos(active_yaw)
        vy = speed * math.sin(active_yaw)
        vz = climb_rate

        # 3. Physically Update Drone Location
        drone.location.x += vx * DT
        drone.location.y += vy * DT
        drone.location.z += vz * DT

        # 4. Update Blender dependency graph
        if IN_BLENDER:
            bpy.context.view_layer.update()


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
                
                # Send packet to P3 Server and get autonomous steering command
                flight_cmd = self.bridge.send_sensor_packet(packet)
                if flight_cmd:
                    self.bridge.apply_flight_command(flight_cmd)

                # Force Blender 3D Viewport to redraw live every frame
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()

                if self.bridge.frame_id % 30 == 0:
                    wp_idx = flight_cmd.get("active_waypoint_idx", "1")
                    wp_name = flight_cmd.get("active_waypoint_name", "Navigating")
                    drone = self.bridge.get_drone_object()
                    loc = drone.location if drone else [0, 0, 0]
                    self.report({'INFO'}, f"Frame #{packet['frame_id']:04d} | Drone '{drone.name if drone else 'None'}': ({loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f})m | WP #{wp_idx}")

            return {'PASS_THROUGH'}

        def execute(self, context):
            wm = context.window_manager
            self._timer = wm.event_timer_add(DT, window=context.window)
            wm.modal_handler_add(self)
            self.bridge.connect_ws()
            
            drone = self.bridge.find_and_bind_drone()
            
            print("\n" + "=" * 65)
            print("         NAVIS BLENDER DRONE SIMULATION BRIDGE           ")
            print("=" * 65)
            print(" [SCENE OBJECTS LIST]:")
            for obj in bpy.data.objects:
                marker = " <--- [CONTROLLED DRONE]" if obj == drone else ""
                print(f"   • '{obj.name}' (Type: {obj.type}){marker}")
            
            if drone:
                print(f"\n >>> TARGETING DRONE OBJECT: '{drone.name}' at Location: {list(drone.location)}")
            else:
                print("\n [WARNING] No Drone Mesh found! Please click/select your drone model in the 3D Viewport.")
            
            print(f" >>> CONNECTING TO: {SERVER_WS_URL}")
            print(" >>> PRESS ESC IN 3D VIEWPORT TO STOP SIMULATION.")
            print("=" * 65 + "\n")
            
            return {'RUNNING_MODAL'}

        def cancel(self, context):
            wm = context.window_manager
            if self._timer is not None:
                wm.event_timer_remove(self._timer)
            if self.bridge.ws is not None:
                try:
                    self.bridge.ws.close()
                except Exception:
                    pass
                self.bridge.ws = None
            print("\n[Navis Blender Bridge] Stopped simulation loop.\n")


def register():
    if IN_BLENDER:
        try:
            bpy.utils.unregister_class(NAVIS_OT_DroneSimulationModal)
        except Exception:
            pass
        bpy.utils.register_class(NAVIS_OT_DroneSimulationModal)
        print("[Navis Blender Bridge] Registered successfully.")

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
        print(f"Testing connection to: {SERVER_WS_URL}")
        cmd = bridge.send_sensor_packet(pkt)
        print(f"Response from P3 Server: {cmd}")
        print("BlenderDroneBridge standalone test complete!")
