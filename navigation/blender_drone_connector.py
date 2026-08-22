"""
NAVIS BLENDER DRONE SIMULATION + TELEMETRY + VIDEO STREAM
=========================================================

P3 SLAM Navigation Server:
    ws://10.247.227.32:8765/ws/sensors

P4 Dashboard Video Stream (or P3 Video Stream):
    ws://10.247.227.40:8000/ws/camera?role=producer  (or ws://10.247.227.32:8765/ws/video)

Fixed Issues:
    1. Cross-platform temp path (fixes Windows /tmp crash).
    2. Realistic network timeout for flight commands (fixes 1ms socket timeout bug).
    3. Auto-reconnection to P3 SLAM server if connection drops.
    4. Non-blocking video transmission queue.
"""

import bpy
import math
import time
import json
import os
import threading
import queue
import websocket

# ============================================================
# CONFIGURATION
# ============================================================

# P3 Server IP (SLAM Navigation & Autopilot)
P3_SERVER_IP = "10.247.227.32"

# P4 Backend IP (Integration Dashboard)
P4_BACKEND_IP = "10.247.227.40"

# Target WebSockets
SERVER_WS_URL = f"ws://{P3_SERVER_IP}:8765/ws/sensors"
# Live camera POV video directly to P4 Dashboard (Port 8000)
VIDEO_WS_URL = f"ws://{P4_BACKEND_IP}:8000/ws/camera?role=producer"

DRONE_OBJECT_NAME = "UAV_ROOT"
CAMERA_OBJECT_NAME = "Camera.001"

FPS = 30
DT = 1.0 / FPS

VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360
JPEG_QUALITY = 60

# ============================================================
# GLOBAL VIDEO STATE
# ============================================================

video_queue = queue.Queue(maxsize=1)
video_thread = None
video_running = False
video_ws = None


# ============================================================
# VIDEO THREAD (NON-BLOCKING)
# ============================================================

def video_sender_thread():
    global video_running, video_ws

    print(f"[VIDEO] Video streamer thread started targeting: {VIDEO_WS_URL}")

    while video_running:
        try:
            frame = video_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            if video_ws is None:
                video_ws = websocket.create_connection(VIDEO_WS_URL, timeout=3)
                print(f"[VIDEO SUCCESS] Connected to video endpoint: {VIDEO_WS_URL}")

            video_ws.send(frame, opcode=websocket.ABNF.OPCODE_BINARY)

        except Exception as e:
            try:
                if video_ws:
                    video_ws.close()
            except Exception:
                pass
            video_ws = None
            time.sleep(2.0)


def start_video_thread():
    global video_running, video_thread
    if video_running:
        return
    video_running = True
    video_thread = threading.Thread(target=video_sender_thread, daemon=True)
    video_thread.start()


def stop_video_thread():
    global video_running, video_ws
    video_running = False
    try:
        if video_ws:
            video_ws.close()
    except Exception:
        pass
    video_ws = None
    print("[VIDEO] Sender thread stopped.")


# ============================================================
# BLENDER DRONE BRIDGE
# ============================================================

class BlenderDroneBridge:

    def __init__(self, drone_name=DRONE_OBJECT_NAME, camera_name=CAMERA_OBJECT_NAME):
        self.drone_name = drone_name
        self.camera_name = camera_name
        self.prev_pos = None
        self.prev_vel = None
        self.prev_time = time.time()
        self.frame_id = 0
        self._drone_obj = None

    def find_and_bind_drone(self):
        if self.drone_name in bpy.data.objects:
            self._drone_obj = bpy.data.objects[self.drone_name]
            return self._drone_obj
        if bpy.context.active_object and bpy.context.active_object.type != 'CAMERA':
            self._drone_obj = bpy.context.active_object
            return self._drone_obj
        for o in bpy.data.objects:
            if o.type != 'CAMERA' and any(k in o.name.lower() for k in ["uav", "drone", "quad", "root", "body"]):
                self._drone_obj = o
                return self._drone_obj
        for o in bpy.data.objects:
            if o.type in ['MESH', 'EMPTY']:
                self._drone_obj = o
                return self._drone_obj
        return None

    def get_drone_object(self):
        if self._drone_obj is None or self._drone_obj.name not in bpy.data.objects:
            self.find_and_bind_drone()
        return self._drone_obj

    def get_camera_object(self):
        return bpy.data.objects.get(self.camera_name) or bpy.context.scene.camera

    def capture_video_frame(self):
        global video_queue
        camera = self.get_camera_object()
        if camera is None:
            return

        scene = bpy.context.scene
        scene.camera = camera
        scene.render.resolution_x = VIDEO_WIDTH
        scene.render.resolution_y = VIDEO_HEIGHT
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'JPEG'
        scene.render.image_settings.quality = JPEG_QUALITY

        # Cross-platform temp path (works on Windows & Linux)
        temp_dir = bpy.app.tempdir if hasattr(bpy.app, "tempdir") and bpy.app.tempdir else os.environ.get("TEMP", "/tmp")
        temp_path = os.path.join(temp_dir, "blender_video_frame.jpg")

        try:
            scene.render.filepath = temp_path
            bpy.ops.render.opengl(write_still=True)

            with open(temp_path, "rb") as f:
                jpeg_bytes = f.read()

            # Push to queue (replace oldest if full)
            try:
                if video_queue.full():
                    video_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                video_queue.put_nowait(jpeg_bytes)
            except queue.Full:
                pass

        except Exception as e:
            pass

    def read_telemetry_and_imu(self):
        drone = self.get_drone_object()
        current_time = time.time()
        dt = max(current_time - self.prev_time, 1e-3)
        self.prev_time = current_time
        self.frame_id += 1

        if drone is not None:
            pos = drone.location
            rot = drone.rotation_euler
            pos_vec = [float(pos.x), float(pos.y), float(pos.z)]
            euler_deg = [math.degrees(rot.x), math.degrees(rot.y), math.degrees(rot.z)]
        else:
            pos_vec = [0.0, 0.0, 5.0]
            euler_deg = [0.0, 0.0, 0.0]

        # Velocity
        if self.prev_pos is not None:
            vel_vec = [(pos_vec[i] - self.prev_pos[i]) / dt for i in range(3)]
        else:
            vel_vec = [0.0, 0.0, 0.0]

        # Acceleration
        if self.prev_vel is not None:
            acc_linear = [(vel_vec[i] - self.prev_vel[i]) / dt for i in range(3)]
        else:
            acc_linear = [0.0, 0.0, 0.0]

        self.prev_pos = list(pos_vec)
        self.prev_vel = list(vel_vec)

        acc_specific_force = {
            "x": round(acc_linear[0], 4),
            "y": round(acc_linear[1], 4),
            "z": round(acc_linear[2] + 9.81, 4)
        }

        # Gyroscope angular velocity (rad/s)
        if hasattr(self, "prev_euler") and self.prev_euler is not None:
            gyro_reading = {
                "x": round(math.radians(euler_deg[0] - self.prev_euler[0]) / dt, 4),
                "y": round(math.radians(euler_deg[1] - self.prev_euler[1]) / dt, 4),
                "z": round(math.radians(euler_deg[2] - self.prev_euler[2]) / dt, 4),
            }
        else:
            gyro_reading = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.prev_euler = list(euler_deg)

        sensor_packet = {
            "frame_id": self.frame_id,
            "timestamp": round(self.frame_id * DT, 4),
            "camera": {
                "image_path": f"frames/frame_{self.frame_id:06d}.jpg",
                "width": VIDEO_WIDTH,
                "height": VIDEO_HEIGHT
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

    def apply_flight_command(self, flight_cmd):
        drone = self.get_drone_object()
        if drone is None or not flight_cmd:
            return

        speed = float(flight_cmd.get("desired_velocity_mps", 0.0))
        target_yaw_deg = float(flight_cmd.get("target_heading_yaw_deg", 0.0))
        target_roll_deg = float(flight_cmd.get("target_roll_deg", 0.0))
        target_pitch_deg = float(flight_cmd.get("target_pitch_deg", 0.0))
        climb_rate = float(flight_cmd.get("climb_rate_mps", 0.0))

        # 1. Smooth Yaw Heading (Aerodynamic rate-limited turning)
        target_yaw_rad = math.radians(target_yaw_deg)
        current_yaw_rad = drone.rotation_euler.z
        yaw_diff = (target_yaw_rad - current_yaw_rad + math.pi) % (2.0 * math.pi) - math.pi

        # 2. Banked Coordinated Turn (Dynamic Roll Inward)
        if abs(target_roll_deg) < 1e-3 and abs(yaw_diff) > 0.01:
            calc_bank = math.degrees(-math.atan2(speed * yaw_diff * 2.2, 9.81))
            target_roll_deg = max(-28.0, min(28.0, calc_bank))

        # 3. Dynamic Forward Pitch & Climb Attitude
        if abs(target_pitch_deg) < 1e-3:
            if speed > 0.1:
                target_pitch_deg = max(-20.0, min(5.0, -2.5 * speed))
            if abs(climb_rate) > 0.2:
                target_pitch_deg += max(-5.0, min(5.0, -climb_rate * 2.0))

        target_roll_rad = math.radians(target_roll_deg)
        target_pitch_rad = math.radians(target_pitch_deg)

        # 4. Apply 6-DOF Physical Inertial Smoothing (Damped Euler Rotation)
        drone.rotation_euler.z += yaw_diff * 0.12                                    # Smooth Yaw
        drone.rotation_euler.x += (target_roll_rad - drone.rotation_euler.x) * 0.15  # Banked Roll
        drone.rotation_euler.y += (target_pitch_rad - drone.rotation_euler.y) * 0.15 # Forward Pitch

        # 5. Advance 3D World Position
        active_yaw = drone.rotation_euler.z
        vx = speed * math.cos(active_yaw)
        vy = speed * math.sin(active_yaw)
        vz = climb_rate

        drone.location.x += vx * DT
        drone.location.y += vy * DT
        drone.location.z += vz * DT

        bpy.context.view_layer.update()


# ============================================================
# WEBSOCKET CLIENT TO P3 SLAM
# ============================================================

sensor_ws = None

def connect_sensor_server():
    global sensor_ws
    try:
        sensor_ws = websocket.create_connection(SERVER_WS_URL, timeout=2.0)
        print(f"\n[P3 SLAM SUCCESS] Connected to P3 Navigation Server: {SERVER_WS_URL}\n")
        return True
    except Exception as e:
        sensor_ws = None
        return False


# ============================================================
# BLENDER MODAL OPERATOR
# ============================================================

class NAVIS_OT_DroneSimulationModal(bpy.types.Operator):
    bl_idname = "navis.drone_simulation_modal"
    bl_label = "Navis Drone Simulation Loop"

    _timer = None
    bridge = BlenderDroneBridge()
    last_reconnect_time = 0

    def modal(self, context, event):
        global sensor_ws

        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            # 1. Read Drone Telemetry & IMU
            packet, gt = self.bridge.read_telemetry_and_imu()

            # 2. Render and push video frame
            self.bridge.capture_video_frame()

            # 3. Auto-Reconnect to P3 SLAM server if disconnected
            now = time.time()
            if sensor_ws is None and (now - self.last_reconnect_time > 2.0):
                self.last_reconnect_time = now
                connect_sensor_server()

            # 4. Send packet to P3 and receive flight command
            flight_cmd = {}
            if sensor_ws is not None:
                try:
                    sensor_ws.send(json.dumps(packet))
                    
                    # Set 50ms timeout for response (plenty for 0.5ms local Wi-Fi, without dropping)
                    sensor_ws.settimeout(0.05)
                    try:
                        response = sensor_ws.recv()
                        if response:
                            data = json.loads(response)
                            flight_cmd = data.get("flight_command", {})
                            self.bridge.apply_flight_command(flight_cmd)
                    except websocket.WebSocketTimeoutException:
                        pass
                except Exception as e:
                    try:
                        sensor_ws.close()
                    except Exception:
                        pass
                    sensor_ws = None

            # 5. Force 3D Viewport Live Redraw
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

            # 6. Status Report
            if self.bridge.frame_id % 15 == 0:
                drone = self.bridge.get_drone_object()
                loc = drone.location if drone else [0, 0, 0]
                p3_status = "ONLINE" if sensor_ws is not None else "CONNECTING..."
                wp = flight_cmd.get("active_waypoint_idx", "-")
                self.report({'INFO'}, f"Frame #{packet['frame_id']:04d} | Drone '{drone.name if drone else 'None'}': ({loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f})m | WP #{wp} | P3: {p3_status}")

        return {'PASS_THROUGH'}

    def execute(self, context):
        # Start Video Thread
        start_video_thread()

        # Connect to P3
        connect_sensor_server()

        wm = context.window_manager
        self._timer = wm.event_timer_add(DT, window=context.window)
        wm.modal_handler_add(self)

        drone = self.bridge.find_and_bind_drone()
        print("\n" + "=" * 65)
        print("         NAVIS BLENDER DRONE SIMULATION + VIDEO BRIDGE   ")
        print("=" * 65)
        print(f" [DRONE OBJECT]:  '{drone.name if drone else 'None'}'")
        print(f" [CAMERA OBJECT]: '{CAMERA_OBJECT_NAME}'")
        print(f" [P3 SLAM URL]:   {SERVER_WS_URL}")
        print(f" [VIDEO WS URL]:  {VIDEO_WS_URL}")
        print(f" [SIMULATION]:    {FPS} FPS (DT = {DT:.4f}s)")
        print(" [INFO] Press ESC in 3D Viewport to stop.")
        print("=" * 65 + "\n")

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        global sensor_ws
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        stop_video_thread()
        if sensor_ws is not None:
            try:
                sensor_ws.close()
            except Exception:
                pass
            sensor_ws = None
        print("\n[Navis Blender Bridge] Simulation stopped.\n")


def register():
    try:
        bpy.utils.register_class(NAVIS_OT_DroneSimulationModal)
    except Exception:
        pass
    print("[Navis] Operator registered successfully.")

def unregister():
    bpy.utils.unregister_class(NAVIS_OT_DroneSimulationModal)


if __name__ == "__main__":
    register()
    bpy.ops.navis.drone_simulation_modal()
