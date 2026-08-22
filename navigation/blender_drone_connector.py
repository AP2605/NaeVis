"""
NAVIS BLENDER DRONE SIMULATION + TELEMETRY + VIDEO + GROUND TRUTH
=================================================================

Multi-Node Pipeline:
  1. P3 SLAM Server (Port 8765):
     ws://10.110.7.32:8765/ws/sensors  --> Sensor Telemetry & 6-DOF Autonomous Steering
  2. P4 Video Stream (Port 8000):
     ws://10.110.7.40:8000/ws/video    --> Raw Binary JPEG Frames from Camera.001
  3. P4 Ground Truth Stream (Port 8000):
     ws://10.110.7.40:8000/ws/groundtruth --> True 6-DOF Simulation Pose & Velocity

Merged Features:
  - Non-blocking Background Video & Ground Truth Streaming Threads.
  - Base64 Frame Encoding in SensorPacket for P3 Visual Odometry / SLAM.
  - Safe Non-blocking Socket Handling (Zero drops/disconnects on transient timeouts).
  - 6-DOF Aerodynamic Banked Turns, Cruise Pitch Tilt & Inertial Smoothing.
  - Cross-Platform OpenGL/Scene Render Frame Capture (Windows & Linux).
"""

import bpy
import math
import time
import json
import os
import threading
import queue
import socket
import base64
import websocket

# ============================================================
# CONFIGURATION — TEAM NETWORK IPS
# ============================================================

# P3 Server IP (SLAM Navigation & Autopilot)
P3_SERVER_IP = "10.110.7.32"

# P4 Backend IP (Integration Dashboard)
P4_BACKEND_IP = "10.110.7.40"

# Target WebSockets
SERVER_WS_URL = f"ws://{P3_SERVER_IP}:8765/ws/sensors"
VIDEO_WS_URL = f"ws://{P4_BACKEND_IP}:8000/ws/video"
GROUNDTRUTH_WS_URL = f"ws://{P4_BACKEND_IP}:8000/ws/groundtruth"

# Blender Objects
DRONE_OBJECT_NAME = "UAV_ROOT"
CAMERA_OBJECT_NAME = "Camera.001"

# Simulation Rate
FPS = 30
DT = 1.0 / FPS

# Camera Resolution
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360
JPEG_QUALITY = 60


# ============================================================
# QUEUES & GLOBAL THREAD STATE
# ============================================================

video_queue = queue.Queue(maxsize=1)
groundtruth_queue = queue.Queue(maxsize=2)

video_running = False
groundtruth_running = False

video_thread = None
groundtruth_thread = None

video_ws = None
groundtruth_ws = None
sensor_ws = None


# ============================================================
# BACKGROUND SENDER: VIDEO (BINARY JPEG)
# ============================================================

def video_sender_thread():
    global video_running, video_ws
    print(f"[VIDEO] Streamer thread started targeting: {VIDEO_WS_URL}")

    while video_running:
        try:
            jpeg_bytes = video_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            if video_ws is None:
                video_ws = websocket.create_connection(VIDEO_WS_URL, timeout=3.0)
                print(f"[VIDEO SUCCESS] Connected to P4: {VIDEO_WS_URL}")

            video_ws.send(jpeg_bytes, opcode=websocket.ABNF.OPCODE_BINARY)

        except Exception:
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


# ============================================================
# BACKGROUND SENDER: GROUND TRUTH (JSON)
# ============================================================

def groundtruth_sender_thread():
    global groundtruth_running, groundtruth_ws
    print(f"[GROUND TRUTH] Streamer thread started targeting: {GROUNDTRUTH_WS_URL}")

    while groundtruth_running:
        try:
            data = groundtruth_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            if groundtruth_ws is None:
                groundtruth_ws = websocket.create_connection(GROUNDTRUTH_WS_URL, timeout=3.0)
                print(f"[GROUND TRUTH SUCCESS] Connected to P4: {GROUNDTRUTH_WS_URL}")

            groundtruth_ws.send(json.dumps(data))

        except Exception:
            try:
                if groundtruth_ws:
                    groundtruth_ws.close()
            except Exception:
                pass
            groundtruth_ws = None
            time.sleep(2.0)


def start_groundtruth_thread():
    global groundtruth_running, groundtruth_thread
    if groundtruth_running:
        return
    groundtruth_running = True
    groundtruth_thread = threading.Thread(target=groundtruth_sender_thread, daemon=True)
    groundtruth_thread.start()


def stop_threads():
    global video_running, groundtruth_running, video_ws, groundtruth_ws
    video_running = False
    groundtruth_running = False

    try:
        if video_ws:
            video_ws.close()
    except Exception:
        pass
    try:
        if groundtruth_ws:
            groundtruth_ws.close()
    except Exception:
        pass

    video_ws = None
    groundtruth_ws = None
    print("[THREADS] Background video and ground truth threads stopped.")


# ============================================================
# BLENDER DRONE BRIDGE
# ============================================================

class BlenderDroneBridge:

    def __init__(self, drone_name=DRONE_OBJECT_NAME, camera_name=CAMERA_OBJECT_NAME):
        self.drone_name = drone_name
        self.camera_name = camera_name
        self.initial_pos = None
        self.prev_pos = None
        self.prev_vel = None
        self.prev_time = time.time()
        self.prev_euler = None
        self.frame_id = 0
        self._drone_obj = None

    def find_and_bind_drone(self):
        # 1. Try explicit names
        for name in [self.drone_name, "UAV_ROOT", "UAV_Root", "UAV_root", "Drone", "drone"]:
            if name in bpy.data.objects:
                self._drone_obj = bpy.data.objects[name]
                return self._drone_obj
        # 2. Check active object if not camera
        if bpy.context.active_object and bpy.context.active_object.type != 'CAMERA':
            self._drone_obj = bpy.context.active_object
            return self._drone_obj
        # 3. Search keywords
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

    def capture_frame(self):
        camera = self.get_camera_object()
        if camera is None:
            return None

        scene = bpy.context.scene
        scene.camera = camera
        scene.render.resolution_x = VIDEO_WIDTH
        scene.render.resolution_y = VIDEO_HEIGHT
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'JPEG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.quality = JPEG_QUALITY

        # Cross-platform safe temp path
        temp_dir = bpy.app.tempdir if hasattr(bpy.app, "tempdir") and bpy.app.tempdir else os.environ.get("TEMP", "/tmp")
        temp_path = os.path.join(temp_dir, "navis_render_frame.jpg")

        try:
            scene.render.filepath = temp_path
            bpy.ops.render.opengl(write_still=True)

            with open(temp_path, "rb") as f:
                return f.read()
        except Exception:
            return None

    def read_telemetry(self):
        drone = self.get_drone_object()
        current_time = time.time()
        dt = max(current_time - self.prev_time, 0.001)
        self.prev_time = current_time
        self.frame_id += 1

        if drone:
            pos = drone.location
            rot = drone.rotation_euler
            x, y, z = float(pos.x), float(pos.y), float(pos.z)
            roll, pitch, yaw = math.degrees(rot.x), math.degrees(rot.y), math.degrees(rot.z)
        else:
            x, y, z = 0.0, 0.0, 5.0
            roll, pitch, yaw = 0.0, 0.0, 0.0

        current_pos = [x, y, z]

        # Anchor origin on first frame
        if not hasattr(self, "initial_pos") or self.initial_pos is None:
            self.initial_pos = [x, y, z]

        rel_x = x - self.initial_pos[0]
        rel_y = y - self.initial_pos[1]
        rel_z = z - self.initial_pos[2]

        # Velocity
        if self.prev_pos is not None:
            velocity = [(current_pos[i] - self.prev_pos[i]) / dt for i in range(3)]
        else:
            velocity = [0.0, 0.0, 0.0]

        # Acceleration
        if self.prev_vel is not None:
            acceleration = [(velocity[i] - self.prev_vel[i]) / dt for i in range(3)]
        else:
            acceleration = [0.0, 0.0, 0.0]

        self.prev_pos = current_pos
        self.prev_vel = velocity

        # Gyroscope
        if self.prev_euler is not None:
            gyro = [
                round(math.radians(roll - self.prev_euler[0]) / dt, 4),
                round(math.radians(pitch - self.prev_euler[1]) / dt, 4),
                round(math.radians(yaw - self.prev_euler[2]) / dt, 4)
            ]
        else:
            gyro = [0.0, 0.0, 0.0]
        self.prev_euler = [roll, pitch, yaw]

        # IMU specific force
        imu = {
            "acceleration": {
                "x": round(acceleration[0], 4),
                "y": round(acceleration[1], 4),
                "z": round(acceleration[2] + 9.81, 4)
            },
            "gyroscope": {
                "x": gyro[0],
                "y": gyro[1],
                "z": gyro[2]
            }
        }

        # Ground Truth Packet for P4 (True 3D World Position)
        ground_truth = {
            "type": "ground_truth",
            "frame_id": self.frame_id,
            "timestamp": round(self.frame_id * DT, 4),
            "position": {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)},
            "orientation": {"roll": round(roll, 4), "pitch": round(pitch, 4), "yaw": round(yaw, 4)},
            "velocity": {"x": round(velocity[0], 4), "y": round(velocity[1], 4), "z": round(velocity[2], 4)}
        }

        # Sensor Packet for P3 (True 3D World Position for world-anchoring)
        sensor_packet = {
            "frame_id": self.frame_id,
            "timestamp": round(self.frame_id * DT, 4),
            "camera": {
                "width": VIDEO_WIDTH,
                "height": VIDEO_HEIGHT
            },
            "imu": imu,
            "sim_position": {
                "x": round(x, 4),
                "y": round(y, 4),
                "z": round(z, 4)
            }
        }

        return sensor_packet, ground_truth

    def apply_flight_command(self, command):
        drone = self.get_drone_object()
        if drone is None or not command:
            return

        speed = float(command.get("desired_velocity_mps", 0.0))
        target_yaw_deg = float(command.get("target_heading_yaw_deg", 0.0))
        target_roll_deg = float(command.get("target_roll_deg", 0.0))
        target_pitch_deg = float(command.get("target_pitch_deg", 0.0))
        climb_rate = float(command.get("climb_rate_mps", 0.0))

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

def connect_p3():
    global sensor_ws
    try:
        sensor_ws = websocket.create_connection(SERVER_WS_URL, timeout=3.0)
        print(f"\n[P3 SLAM SUCCESS] Connected to P3 Navigation Server: {SERVER_WS_URL}\n")
        return True
    except Exception as e:
        sensor_ws = None
        return False


def queue_video(jpeg_bytes):
    if jpeg_bytes is None:
        return
    try:
        if video_queue.full():
            video_queue.get_nowait()
    except queue.Empty:
        pass
    try:
        video_queue.put_nowait(jpeg_bytes)
    except queue.Full:
        pass


def queue_ground_truth(data):
    if data is None:
        return
    try:
        if groundtruth_queue.full():
            groundtruth_queue.get_nowait()
    except queue.Empty:
        pass
    try:
        groundtruth_queue.put_nowait(data)
    except queue.Full:
        pass


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
            # 1. READ TELEMETRY & IMU + GROUND TRUTH
            sensor_packet, ground_truth = self.bridge.read_telemetry()

            # 2. CAPTURE CAMERA FRAME
            jpeg_bytes = None
            if self.bridge.frame_id % 2 == 0:
                jpeg_bytes = self.bridge.capture_frame()

            # 3. QUEUE VIDEO TO P4 DASHBOARD
            if jpeg_bytes is not None:
                queue_video(jpeg_bytes)

            # 4. QUEUE GROUND TRUTH TO P4 DASHBOARD
            queue_ground_truth(ground_truth)

            # 5. AUTO-RECONNECT TO P3 IF DISCONNECTED
            now = time.time()
            if sensor_ws is None and (now - self.last_reconnect_time > 2.0):
                self.last_reconnect_time = now
                connect_p3()

            # 6. SEND TO P3 SLAM & RECEIVE AUTONOMOUS FLIGHT COMMAND
            flight_cmd = {}
            if sensor_ws is not None:
                try:
                    if jpeg_bytes is not None:
                        sensor_packet["camera"]["image_base64"] = base64.b64encode(jpeg_bytes).decode("utf-8")
                        sensor_packet["camera"]["format"] = "jpeg"

                    sensor_ws.send(json.dumps(sensor_packet))

                    # Safe non-blocking receive (timeout 0.3s)
                    sensor_ws.settimeout(0.3)
                    try:
                        response = sensor_ws.recv()
                        if response:
                            data = json.loads(response)
                            flight_cmd = data.get("flight_command", {})
                            self.bridge.apply_flight_command(flight_cmd)
                    except (websocket.WebSocketTimeoutException, socket.timeout, TimeoutError, BlockingIOError):
                        pass

                except Exception as e:
                    print(f"[P3 SLAM Disconnect Error]: {e}")
                    try:
                        sensor_ws.close()
                    except Exception:
                        pass
                    sensor_ws = None

            # 7. FORCE 3D VIEWPORT LIVE REDRAW
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

            # 8. STATUS LOGGING
            if self.bridge.frame_id % 15 == 0:
                pos = ground_truth["position"]
                p3_status = "ONLINE" if sensor_ws is not None else "CONNECTING..."
                vid_status = "ONLINE" if video_ws is not None else "OFFLINE"
                gt_status = "ONLINE" if groundtruth_ws is not None else "OFFLINE"
                wp = flight_cmd.get("active_waypoint_idx", "-")
                self.report({'INFO'}, f"Frame #{self.bridge.frame_id:04d} | Pos: ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f})m | WP #{wp} | P3: {p3_status} | Video: {vid_status} | GT: {gt_status}")

        return {'PASS_THROUGH'}

    def execute(self, context):
        start_video_thread()
        start_groundtruth_thread()
        connect_p3()

        wm = context.window_manager
        self._timer = wm.event_timer_add(DT, window=context.window)
        wm.modal_handler_add(self)

        drone = self.bridge.find_and_bind_drone()
        print("\n" + "=" * 65)
        print("    NAVIS BLENDER DRONE SIMULATION (VIDEO + GT + P3 SLAM)   ")
        print("=" * 65)
        print(f" [DRONE OBJECT]:       '{drone.name if drone else 'None'}'")
        print(f" [CAMERA OBJECT]:      '{CAMERA_OBJECT_NAME}'")
        print(f" [P3 SLAM URL]:        {SERVER_WS_URL}")
        print(f" [P4 VIDEO URL]:       {VIDEO_WS_URL}")
        print(f" [P4 GROUNDTRUTH URL]: {GROUNDTRUTH_WS_URL}")
        print(f" [SIMULATION]:         {FPS} FPS (DT = {DT:.4f}s)")
        print(" [INFO] Press ESC in 3D Viewport to stop.")
        print("=" * 65 + "\n")

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        global sensor_ws
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None

        stop_threads()

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
    stop_threads()
    try:
        bpy.utils.unregister_class(NAVIS_OT_DroneSimulationModal)
    except Exception:
        pass


if __name__ == "__main__":
    register()
    bpy.ops.navis.drone_simulation_modal()
