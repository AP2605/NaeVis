"""
NAVIS BLENDER DRONE SIMULATION + TELEMETRY + VIDEO STREAM
=========================================================

P3 / SLAM:
    ws://10.247.227.32:8765/ws/sensors

VIDEO STREAM (P3 / P4):
    ws://10.247.227.32:8765/ws/video  (or ws://10.247.227.40:8000/ws/video)

Features:
    - 15/30 FPS simulation loop
    - Drone telemetry & IMU simulation
    - Bidirectional P3 SLAM navigation & autonomous flight command execution
    - Non-blocking background video WebSocket streaming thread
    - Automatic object binding (UAV_ROOT & Camera.001)
    - Live 3D Viewport redrawing
"""

import math
import time
import json
import os
import threading

try:
    import bpy
    import mathutils
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False
    print("[ERROR] This script must be run inside Blender.")

try:
    import websocket
    HAS_WEBSOCKET_CLIENT = True
except ImportError:
    HAS_WEBSOCKET_CLIENT = False


# ============================================================
# CONFIGURATION
# ============================================================

# P3 Navigation / SLAM Server IP
P3_SERVER_IP = "10.247.227.32"

SERVER_WS_URL = f"ws://{P3_SERVER_IP}:8765/ws/sensors"
VIDEO_WS_URL = f"ws://{P3_SERVER_IP}:8765/ws/video"

# Blender 3D Objects
DRONE_OBJECT_NAME = "UAV_ROOT"
CAMERA_OBJECT_NAME = "Camera.001"

# Simulation Rate
FPS = 30
DT = 1.0 / FPS

# Video Streaming Settings
SEND_VIDEO_FRAMES = True
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360
VIDEO_JPEG_QUALITY = 60


# ============================================================
# VIDEO STREAMER (NON-BLOCKING BACKGROUND THREAD)
# ============================================================

class VideoStreamer:
    """
    Sends the latest available binary JPEG frame through a WebSocket
    in a background thread without blocking the Blender physics loop.
    """

    def __init__(self, url=VIDEO_WS_URL):
        self.url = url
        self.ws = None
        self.connected = False
        self.running = True
        self.latest_frame = None
        self.lock = threading.Lock()

        if HAS_WEBSOCKET_CLIENT and SEND_VIDEO_FRAMES:
            self.thread = threading.Thread(target=self._sender_loop, daemon=True)
            self.thread.start()
            print(f"[VIDEO] Background streamer started targeting: {self.url}")

    def connect(self):
        if not HAS_WEBSOCKET_CLIENT:
            return
        try:
            self.ws = websocket.create_connection(self.url, timeout=2.0)
            self.connected = True
            print(f"[VIDEO SUCCESS] Connected to video endpoint: {self.url}")
        except Exception:
            self.connected = False
            self.ws = None

    def update_frame(self, frame_bytes):
        if frame_bytes is None:
            return
        with self.lock:
            self.latest_frame = frame_bytes

    def _sender_loop(self):
        while self.running:
            if not self.connected:
                self.connect()
                if not self.connected:
                    time.sleep(2.0)
                    continue

            frame = None
            with self.lock:
                if self.latest_frame is not None:
                    frame = self.latest_frame
                    self.latest_frame = None

            if frame is None:
                time.sleep(0.005)
                continue

            try:
                self.ws.send(frame, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception:
                self.connected = False
                if self.ws is not None:
                    try:
                        self.ws.close()
                    except Exception:
                        pass
                    self.ws = None

    def close(self):
        self.running = False
        self.connected = False
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None


# ============================================================
# BLENDER DRONE BRIDGE (TELEMETRY & FLIGHT CONTROL)
# ============================================================

class BlenderDroneBridge:
    """
    Manages telemetry extraction, IMU simulation, P3 communication,
    and autonomous flight command execution inside Blender.
    """

    def __init__(self, drone_name=DRONE_OBJECT_NAME, camera_name=CAMERA_OBJECT_NAME):
        self.drone_name = drone_name
        self.camera_name = camera_name
        self.prev_pos = None
        self.prev_vel = None
        self.prev_time = time.time()
        self.frame_id = 0
        self.ws = None
        self.connection_ok = False
        self._drone_obj = None

    def connect_ws(self):
        """Connects to P3 SLAM server on SERVER_WS_URL."""
        if HAS_WEBSOCKET_CLIENT and self.ws is None:
            try:
                self.ws = websocket.create_connection(SERVER_WS_URL, timeout=2.0)
                self.connection_ok = True
                print(f"[P3 SLAM SUCCESS] Connected to P3 Navigation Engine: {SERVER_WS_URL}")
            except Exception as e:
                self.ws = None
                self.connection_ok = False
                print(f"[P3 SLAM ERROR] Could not connect to {SERVER_WS_URL}: {e}")

    def find_and_bind_drone(self):
        if not IN_BLENDER:
            return None

        # 1. Try explicit name
        if self.drone_name in bpy.data.objects:
            self._drone_obj = bpy.data.objects[self.drone_name]
            return self._drone_obj

        # 2. Check active object if not camera
        if bpy.context.active_object and bpy.context.active_object.type != 'CAMERA':
            self._drone_obj = bpy.context.active_object
            return self._drone_obj

        # 3. Search keywords (uav, drone, quad, root, body)
        for o in bpy.data.objects:
            if o.type != 'CAMERA' and any(k in o.name.lower() for k in ["uav", "drone", "quad", "root", "body"]):
                self._drone_obj = o
                return self._drone_obj

        # 4. Fallback to first non-camera object
        for o in bpy.data.objects:
            if o.type in ['MESH', 'EMPTY']:
                self._drone_obj = o
                return self._drone_obj

        return None

    def get_drone_object(self):
        if self._drone_obj is None or (IN_BLENDER and self._drone_obj.name not in bpy.data.objects):
            self.find_and_bind_drone()
        return self._drone_obj

    def get_camera_object(self):
        if not IN_BLENDER:
            return None
        return bpy.data.objects.get(self.camera_name) or bpy.context.scene.camera

    def read_telemetry_and_imu(self):
        """Reads drone 3D position and simulates 6-axis IMU measurements."""
        drone = self.get_drone_object()
        current_time = time.time()
        dt = max(current_time - self.prev_time, 0.001)
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

        # Accelerometer Specific Force (+9.81 m/s^2 reaction force)
        acc_specific_force = {
            "x": round(acc_linear[0], 4),
            "y": round(acc_linear[1], 4),
            "z": round(acc_linear[2] + 9.81, 4)
        }

        # Gyroscope
        gyro_reading = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0
        }

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

    def send_sensor_packet(self, packet: dict) -> dict:
        """Sends SensorPacket to P3 SLAM server and receives autonomous flight command."""
        if not HAS_WEBSOCKET_CLIENT:
            return {}

        if self.ws is None:
            self.connect_ws()

        if self.ws is not None:
            try:
                self.ws.send(json.dumps(packet))
                resp = json.loads(self.ws.recv())
                self.connection_ok = True
                return resp.get("flight_command", {})
            except Exception:
                self.ws = None
                self.connection_ok = False

        return {}

    def apply_flight_command(self, flight_cmd: dict):
        """Applies P3's autonomous flight command to physically move the drone in Blender."""
        drone = self.get_drone_object()
        if drone is None or not flight_cmd or "desired_velocity_mps" not in flight_cmd:
            return

        speed = float(flight_cmd.get("desired_velocity_mps", 0.0))
        target_yaw_deg = float(flight_cmd.get("target_heading_yaw_deg", 0.0))
        climb_rate = float(flight_cmd.get("climb_rate_mps", 0.0))

        # 1. Rotate Heading towards Target Waypoint
        target_yaw_rad = math.radians(target_yaw_deg)
        current_yaw_rad = drone.rotation_euler.z
        yaw_diff = (target_yaw_rad - current_yaw_rad + math.pi) % (2.0 * math.pi) - math.pi
        drone.rotation_euler.z += yaw_diff * 0.15

        # 2. Advance Drone Location
        active_yaw = drone.rotation_euler.z
        vx = speed * math.cos(active_yaw)
        vy = speed * math.sin(active_yaw)
        vz = climb_rate

        drone.location.x += vx * DT
        drone.location.y += vy * DT
        drone.location.z += vz * DT

        # 3. Update Scene Dependency Graph
        if IN_BLENDER:
            bpy.context.view_layer.update()


# ============================================================
# RENDER CAMERA FRAME (JPEG ENCODING)
# ============================================================

def render_camera_frame():
    """Renders the camera viewport and returns JPEG bytes."""
    if not IN_BLENDER:
        return None

    scene = bpy.context.scene
    camera = bpy.data.objects.get(CAMERA_OBJECT_NAME)
    if camera is not None:
        scene.camera = camera

    scene.render.resolution_x = VIDEO_WIDTH
    scene.render.resolution_y = VIDEO_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'JPEG'
    scene.render.image_settings.quality = VIDEO_JPEG_QUALITY

    try:
        temp_path = os.path.join(bpy.app.tempdir, "navis_current_frame.jpg")
        scene.render.filepath = temp_path
        bpy.ops.render.opengl(write_still=True)
        with open(temp_path, "rb") as f:
            return f.read()
    except Exception:
        return None


# ============================================================
# BLENDER MODAL OPERATOR
# ============================================================

if IN_BLENDER:
    class NAVIS_OT_DroneSimulationModal(bpy.types.Operator):
        bl_idname = "navis.drone_simulation_modal"
        bl_label = "Navis Drone Simulation Loop"

        _timer = None
        bridge = BlenderDroneBridge()
        video_streamer = VideoStreamer(VIDEO_WS_URL)

        def modal(self, context, event):
            if event.type == 'ESC':
                self.cancel(context)
                return {'CANCELLED'}

            if event.type == 'TIMER':
                # 1. READ TELEMETRY & IMU
                packet, gt = self.bridge.read_telemetry_and_imu()

                # 2. SEND TO P3 SLAM SERVER & EXECUTE AUTONOMOUS FLIGHT COMMAND
                flight_cmd = self.bridge.send_sensor_packet(packet)
                if flight_cmd:
                    self.bridge.apply_flight_command(flight_cmd)

                # 3. RENDER & STREAM VIDEO (NON-BLOCKING)
                if SEND_VIDEO_FRAMES and self.bridge.frame_id % 2 == 0:
                    frame_bytes = render_camera_frame()
                    if frame_bytes is not None:
                        self.video_streamer.update_frame(frame_bytes)

                # 4. FORCE 3D VIEWPORT LIVE REDRAW
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()

                # 5. STATUS REPORT
                if self.bridge.frame_id % 15 == 0:
                    drone = self.bridge.get_drone_object()
                    loc = drone.location if drone else [0, 0, 0]
                    p3_stat = "CONNECTED" if self.bridge.connection_ok else "DISCONNECTED"
                    vid_stat = "STREAMING" if self.video_streamer.connected else "OFFLINE"
                    wp_idx = flight_cmd.get("active_waypoint_idx", "-")
                    self.report({'INFO'}, f"Frame #{packet['frame_id']:04d} | Pos: ({loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f})m | WP: #{wp_idx} | P3: {p3_stat} | Video: {vid_stat}")

            return {'PASS_THROUGH'}

        def execute(self, context):
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

            self.bridge.connect_ws()
            return {'RUNNING_MODAL'}

        def cancel(self, context):
            wm = context.window_manager
            if self._timer is not None:
                wm.event_timer_remove(self._timer)
                self._timer = None
            self.video_streamer.close()
            if self.bridge.ws is not None:
                try:
                    self.bridge.ws.close()
                except Exception:
                    pass
                self.bridge.ws = None
            print("\n[Navis Blender Bridge] Simulation stopped.\n")


def register():
    if IN_BLENDER:
        try:
            bpy.utils.unregister_class(NAVIS_OT_DroneSimulationModal)
        except Exception:
            pass
        bpy.utils.register_class(NAVIS_OT_DroneSimulationModal)
        print("[Navis] Operator registered successfully.")

def unregister():
    if IN_BLENDER:
        bpy.utils.unregister_class(NAVIS_OT_DroneSimulationModal)


if __name__ == "__main__":
    if IN_BLENDER:
        register()
        bpy.ops.navis.drone_simulation_modal()
    else:
        print("=== Testing BlenderDroneBridge (Standalone Mode) ===")
        bridge = BlenderDroneBridge()
        pkt, gt = bridge.read_telemetry_and_imu()
        print(f"Generated SensorPacket: {json.dumps(pkt, indent=2)}")
        print(f"Testing connection to: {SERVER_WS_URL}")
        cmd = bridge.send_sensor_packet(pkt)
        print(f"Response from P3 Server: {cmd}")
