# SIH-NAVIS — P4 Integration Backend & Ground Station

Integration backend and real-time ground station service for the **SIH-NAVIS** GPS-denied autonomous drone navigation system. It coordinates and synchronizes:
- **P1 (ML / Perception)**: Terrain classification, semantic segmentation, landmarks, place recognition, localization hints.
- **P2 (Blender Simulation)**: 6-DoF ground truth state, simulated LiDAR, binary JPEG camera stream (~15 FPS).
- **P3 (Navigation / SLAM)**: 6-DoF state estimation, trajectory tracking, mission waypoint guidance.
- **P4 (Integration & Dashboard)**: Multi-rate frame synchronizer, ATE/RPE drift analytics, mission lifecycle management, interactive 3D Three.js dashboard.

---

## 1. Architecture Overview

```text
                           P2 — BLENDER SIMULATION
                                      |
                      +---------------+---------------+
                      |                               |
                /ws/sensors                      /ws/video
             telemetry/control                binary JPEG (~15 FPS)
                      |                               |
                      v                               v
                   P3 SLAM                         P4 BACKEND
            (navigation.server)             (camera fan-out & sync)
                      |                               |
                      v (estimated pose)              |
             +--------+--------+                      |
             |                 |                      |
             v                 v                      v
     /api/v1/navigation   /ws/telemetry       /ws/camera / /ws/video
             |                 |                      |
             +--------+--------+                      |
                      |                               |
                      v                               v
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

---

## 2. Modes of Operation

### Mode A: Mock / Regression Mode (Self-Contained)
Runs P4 backend, frontend, and synthetic mock data producers without requiring teammate hardware:

```powershell
# 1. Start P4 Backend
cd Integration/backend
.\venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Start P4 Frontend
cd Integration/frontend
npm run dev

# 3. Start Mock Producers (P1 + P2 + P3 + Camera)
cd Integration/backend
.\venv\Scripts\python mocks/run_all_mocks.py
```

### Mode B: Real Teammate Integration Mode (LAN / Hardware-in-the-loop)
When testing with real teammates over local network (LAN):

1. **P4 Backend**:
   ```powershell
   cd Integration/backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. **P2 Blender Camera Feed**:
   P2 Blender connects to `ws://<P4-LAN-IP>:8000/ws/video?source=real` pushing binary JPEG frames (~15 FPS).
3. **P3 Navigation Engine**:
   P3 transmits estimated poses to `http://<P4-LAN-IP>:8000/api/v1/navigation/state?source=real` or connects to `/ws/telemetry`.
4. **P1 Perception Service**:
   P1 posts vision results to `http://<P4-LAN-IP>:8000/api/v1/perception/result?source=real`.
5. **P4 Dashboard**:
   Open browser at `http://<P4-LAN-IP>:3000` (or `http://localhost:3000`).

---

## 3. Endpoints & Protocol Reference

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root system status |
| `GET` | `/health` | Backend liveness probe |
| `GET` | `/telemetry` | Current estimated drone pose & velocity |
| `POST` | `/api/v1/perception/result` | Ingest P1 perception packet |
| `GET` | `/api/v1/perception/latest` | Retrieve latest P1 perception result |
| `POST` | `/api/v1/simulation/ground-truth` | Ingest P2 simulation ground truth |
| `GET` | `/api/v1/simulation/ground-truth/latest` | Retrieve latest P2 ground truth |
| `POST` | `/api/v1/navigation/state` | Ingest P3 estimated pose & velocity |
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

| Protocol | Path | Direction | Description |
|---|---|---|---|
| `WS` | `/ws/telemetry` | Outbound | 10 Hz JSON broadcast of telemetry, integrated state, analytics, mission events |
| `WS` | `/ws/video` | In / Out | High-throughput binary optical video stream for frontend viewer & P2 producer |
| `WS` | `/ws/camera` | In / Out | Backward-compatible raw JPEG camera stream |
| `WS` | `/ws/slam` | Outbound | Structured binary packets (`NAVC` header + JPEG payload) for visual SLAM |

---

## 4. Source Health & Stale Detection

Source health states are exposed via `/api/v1/integration/health` and live WebSocket updates:

- `CONNECTED`: Actively receiving packets from verified real teammate source within `STALE_TIMEOUT_SEC`.
- `MOCK`: Actively receiving packets from synthetic mock producers.
- `STALE`: No packets received within `STALE_TIMEOUT_SEC` (default: 3.0s).
- `DISCONNECTED`: No connection established or source terminated.
- `ERROR`: Ingestion failed or malformed stream.

---

## 5. Configuration Settings

Configurable via environment variables (in `app/config.py`):

| Variable | Default | Description |
|---|---|---|
| `P4_HOST` | `0.0.0.0` | Host binding for LAN accessibility |
| `P4_PORT` | `8000` | Server HTTP/WebSocket port |
| `STALE_TIMEOUT_SEC` | `3.0` | Timeout threshold in seconds before source becomes STALE |
| `CAMERA_MAX_FRAME_SIZE` | `10485760` | Maximum allowable binary frame size (10 MB) |
| `SOURCE_MODE` | `AUTO` | Source detection mode (`AUTO`, `MOCK`, `REAL`) |
| `TELEMETRY_STREAM_INTERVAL` | `0.1` | Telemetry WebSocket push interval (10 Hz) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 6. Running Tests

```bash
# Run complete test suite (91 tests across M1-M6)
pytest tests/ -v
```
