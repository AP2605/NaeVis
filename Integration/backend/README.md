# SIH-NAVIS — P4 Integration Backend & Ground Station

Integration backend and real-time ground station service for the **SIH-NAVIS** GPS-denied autonomous drone navigation system. It coordinates and synchronizes:
- **P1 (ML / Perception)**: Terrain classification, semantic segmentation, landmarks, place recognition, localization hints.
- **P2 (Blender Simulation)**: 6-DoF ground truth state, simulated LiDAR, binary JPEG camera stream (~15 FPS).
- **P3 (Navigation / SLAM)**: 6-DoF state estimation, trajectory tracking, mission waypoint guidance.
- **P4 (Integration & Dashboard)**: Multi-rate frame synchronizer, ATE/RPE drift analytics, mission lifecycle management, interactive 3D Three.js dashboard.

---

## 1. Architecture Overview & Port Separation

```text
                           P2 — BLENDER SIMULATION
                                      |
                      +---------------+---------------+
                      |                               |
                 P2 SENSORS                      /ws/video (PORT 8000)
             telemetry/control                binary JPEG (~15 FPS)
                      |                               |
                      v                               v
                   P3 SLAM                         P4 BACKEND
            (navigation.server)             (camera fan-out & sync)
                      |                               |
                      v JSON WebSocket                |
                 PORT 8004                            |
              /ws/navigation                          |
                      |                               |
                      +---------------+---------------+
                                      |
                                      v
                               P4 INTEGRATION
                          (P3 Adapter & Sync Layer)
                                      |
             +-----------------+-------------+-----------------+
             |   Telemetry     |  Analytics  | Mission Control |
             +-----------------+-------------+-----------------+
                                       |
                                       v
                                  P4 FRONTEND
                                (Next.js 14)
                                       |
             +----------------+--------+--------+----------------+
             |                |                 |                |
             v                v                 v                v
        Live Camera    3D Navigation        Analytics        Telemetry
      (640x480 video)  (Est vs GT Trails)  (ATE/RPE/Drift)   & Health
```

### Dedicated Network Port Allocation

| Module / Service | Host Binding | Port | Protocol & Endpoint | Direction | Description |
|---|---|---|---|---|---|
| **P4 Main API & Camera** | `0.0.0.0` | `8000` | HTTP REST (`/api/v1/*`) & WS (`/ws/video`, `/ws/telemetry`) | In / Out | Main REST API, P2 camera stream, and Frontend telemetry broadcast |
| **P4 Navigation Receiver** | `0.0.0.0` | `8004` | WebSocket (`/ws/navigation`) | Inbound | Dedicated high-throughput listener for P3 SLAM / Navigation telemetry |
| **P4 Frontend Dashboard** | `0.0.0.0` | `3000` | HTTP / Next.js 14 Web App | Outbound | Interactive 3D ground station UI |

---

## 2. P3 Navigation WebSocket Contract (`ws://<P4-IP>:8004/ws/navigation`)

P3 SLAM transmits JSON text messages at its natural estimation rate.

### Payload Schema
```json
{
  "frame_id": 125,
  "timestamp": 4.166,
  "estimated_pose": {
    "x": 10.42,
    "y": 5.81,
    "z": 20.13,
    "roll": 0.3,
    "pitch": -1.1,
    "yaw": 89.7
  },
  "velocity": {
    "x": 3.2,
    "y": 0.0,
    "z": 0.1
  },
  "tracking_state": "TRACKING_GOOD",
  "confidence": 0.96,
  "processing_time_ms": 0.4
}
```

---

## 3. Modes of Operation

### Mode A: Mock / Self-Contained Mode
Runs full simulation with mock producers for P1, P2 ground truth, P2 camera, and P3 navigation:

```powershell
# 1. Start P4 Backend (starts both port 8000 and port 8004 listener)
cd Integration/backend
.\venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Start P4 Frontend
cd Integration/frontend
npm run dev

# 3. Start Mock Producers (P1, P2 GT, P2 Camera, P3 Nav WS)
cd Integration/backend
.\venv\Scripts\python mocks/run_all_mocks.py --p3-mode ws
```

### Mode B: Real Teammate Integration Mode (LAN)
When connecting real teammate machines over local network:

1. **P4 Backend Host**:
   ```powershell
   cd Integration/backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. **P2 Blender Machine**:
   Connects to `ws://<P4-LAN-IP>:8000/ws/video?source=real` pushing binary JPEG frames (~15 FPS).
3. **P3 SLAM Machine**:
   Connects to `ws://<P4-LAN-IP>:8004/ws/navigation?source=real` streaming JSON estimated pose packets.
4. **P1 Perception Machine**:
   Posts vision results to `http://<P4-LAN-IP>:8000/api/v1/perception/result?source=real`.
5. **P4 Ground Station Operator**:
   Opens `http://<P4-LAN-IP>:3000` (or `http://localhost:3000`).

---

## 4. Windows Firewall & LAN Troubleshooting

If incoming TCP connections to port 8000 or 8004 are blocked by Windows Firewall on the P4 host machine, run PowerShell as Administrator:

```powershell
# Allow inbound TCP port 8000 (API + Video + Telemetry)
New-NetFirewallRule -DisplayName "P4 Main API and Video (8000)" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow

# Allow inbound TCP port 8004 (P3 Navigation WebSocket)
New-NetFirewallRule -DisplayName "P4 Navigation Listener (8004)" -Direction Inbound -LocalPort 8004 -Protocol TCP -Action Allow
```

---

## 5. Endpoints & Protocol Reference

### REST Endpoints (Port 8000)

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root system status |
| `GET` | `/health` | Backend liveness probe |
| `GET` | `/telemetry` | Current estimated drone pose & velocity |
| `POST` | `/api/v1/perception/result` | Ingest P1 perception packet |
| `GET` | `/api/v1/perception/latest` | Retrieve latest P1 perception result |
| `POST` | `/api/v1/simulation/ground-truth` | Ingest P2 simulation ground truth |
| `GET` | `/api/v1/simulation/ground-truth/latest` | Retrieve latest P2 ground truth |
| `POST` | `/api/v1/navigation/state` | REST fallback for P3 navigation state |
| `GET` | `/api/v1/navigation/state/latest` | Retrieve latest P3 navigation state |
| `GET` | `/api/v1/integration/state` | Composite system state across all modules |
| `GET` | `/api/v1/integration/health` | Explicit source health status (P1, P2, P3, Camera) |
| `GET` | `/api/v1/integration/camera/stats` | Camera FPS, consumer count, frame age |
| `GET` | `/api/v1/integration/frames` | Ring buffer of synchronized frames |
| `POST` | `/api/v1/integration/reset` | Clear synchronization and trajectory buffers |
| `POST` | `/api/v1/missions` | Create and validate flight mission |
| `GET` | `/api/v1/missions/{id}` | Get mission definition and waypoint progress |
| `GET` | `/api/v1/analytics/metrics` | Compute ATE, RPE, drift, and orientation error |
| `GET` | `/api/v1/trajectory` | Retrieve historical estimated and ground-truth trails |

### WebSocket Endpoints

| Port | Path | Direction | Payload Format | Description |
|---|---|---|---|---|
| `8004` | `/ws/navigation` | Inbound (P3 $\rightarrow$ P4) | JSON Text | Dedicated P3 SLAM / Navigation stream |
| `8000` | `/ws/video` | In / Out | Binary JPEG / NAVC | P2 Blender video stream & frontend display |
| `8000` | `/ws/telemetry` | Outbound (P4 $\rightarrow$ UI) | JSON Events | 10 Hz telemetry, trajectory, analytics broadcast |
| `8000` | `/ws/camera` | In / Out | Binary JPEG | Legacy raw camera viewer stream |
| `8000` | `/ws/slam` | Outbound | Binary NAVC | Synchronized video packets for SLAM |

---

## 6. Running Tests

```bash
# Run complete test suite (98 tests across M1-M6 + P3 WS server)
pytest tests/ -v
```
