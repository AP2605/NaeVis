# SIH-NAVIS — P4 Milestone 2 Report: Real-Time Backend & WebSocket Telemetry

---

## 1. Milestone Summary

Milestone 2 establishes the real-time telemetry backbone for the **SIH-NAVIS** GPS-denied autonomous drone navigation simulation system. We implemented:
- An asynchronous WebSocket connection manager with multi-client support and graceful disconnect recovery.
- A standardized, extensible WebSocket event envelope (`event`, `timestamp`, `data`).
- A high-frequency real-time telemetry stream at `/ws/telemetry` driven by the existing `TelemetryService`.
- Centralized application configuration supporting configurable streaming rates (default 10 Hz / 100 ms).
- Non-blocking client messaging handling (e.g. `ping`/`pong`) and structured event logging.
- Comprehensive automated test coverage (11 unit and integration tests) alongside full manual verification.

---

## 2. Files Created / Modified

| File | Type | Purpose |
|---|---|---|
| `Integration/backend/app/config.py` | Created | Central configuration for app metadata and telemetry stream intervals. |
| `Integration/backend/app/schemas/websocket.py` | Created | Pydantic event envelope (`WebSocketEvent`, `TelemetryEvent`, `WebSocketClientMessage`). |
| `Integration/backend/app/websocket/manager.py` | Created | `ConnectionManager` handling client tracking, personal sends, broadcasts, and error isolation. |
| `Integration/backend/app/websocket/telemetry.py` | Created | `/ws/telemetry` async streaming route with ping/pong and disconnect management. |
| `Integration/backend/app/main.py` | Modified | Registered WebSocket router, imported configuration, and configured application logging. |
| `Integration/backend/tests/test_health.py` | Modified | Root and health probe test cases. |
| `Integration/backend/tests/test_telemetry.py` | Created | REST `/telemetry` endpoint and service generation test cases. |
| `Integration/backend/tests/test_websocket.py` | Created | WebSocket connection, streaming, multi-client, and disconnect resilience tests. |
| `Integration/backend/README.md` | Modified | Updated instructions including WebSocket endpoints and event schema details. |

---

## 3. Architecture

```text
                    ┌───────────────────────────┐
                    │  MockTelemetryGenerator   │
                    │ (Simulated Trajectory)    │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │     TelemetryService      │
                    │ (Integration Abstraction) │
                    └──────┬─────────────┬──────┘
                           │             │
              ┌────────────┘             └────────────┐
              ▼                                       ▼
     ┌──────────────────┐                   ┌──────────────────┐
     │   REST Router    │                   │ WebSocket Router │
     │  GET /telemetry  │                   │  /ws/telemetry   │
     └────────┬─────────┘                   └────────┬─────────┘
              │                                       │
              │                                       ▼
              │                             ┌──────────────────┐
              │                             │ConnectionManager │
              │                             └────────┬─────────┘
              │                                      │
              │                             ┌────────┼────────┐
              ▼                             ▼        ▼        ▼
       [REST Client]                     [UI 1]   [UI 2]   [UI 3]
```

The design ensures the frontend can consume telemetry via REST or WebSockets without depending on whether the telemetry origin is the `MockTelemetryGenerator` or future Unreal Engine / AirSim / SLAM pipelines.

---

## 4. WebSocket Contract

### Endpoint
`ws://127.0.0.1:8000/ws/telemetry`

### Envelope Structure
```json
{
  "event": "telemetry",
  "timestamp": "2026-08-17T12:49:04.549278Z",
  "data": {
    "x": 0.152,
    "y": 0.285,
    "z": 9.965,
    "velocity": 2.65,
    "roll": 0.58,
    "pitch": 2.85,
    "yaw": 0.94,
    "confidence": 0.95,
    "timestamp": "2026-08-17T12:49:04.549278Z"
  }
}
```

### Client Messages Supported
- `{"type": "ping"}` → Responses with `{"type": "pong", "timestamp": "<UTC_ISO_STRING>"}`.

---

## 5. Configuration

Configured in `Integration/backend/app/config.py`:
- `TELEMETRY_STREAM_INTERVAL`: `0.1` (100 ms interval = 10 messages/sec). Can be overridden using the `TELEMETRY_STREAM_INTERVAL` environment variable.
- `LOG_LEVEL`: `INFO`

---

## 6. Testing Results

### Test Suite Execution
- **Command**: `pytest -v` (from `Integration/backend` using the project's venv)
- **Total Tests**: 11
- **Passed**: 11
- **Failed**: 0

### Breakdown
- **REST Endpoints (`test_health.py`, `test_telemetry.py`)**:
  - Root endpoint status and metadata (`GET /`): PASSED
  - Health check probe (`GET /health`): PASSED
  - REST telemetry schema validation (`GET /telemetry`): PASSED
  - TelemetryService state generation: PASSED
- **WebSocket Functionality (`test_websocket.py`)**:
  - Connection & event envelope schema validation: PASSED
  - Continuous streaming & temporal evolution (multi-message): PASSED
  - Ping / pong client message handling: PASSED
  - Malformed / non-JSON input resilience (no server crash): PASSED
  - Multi-client simultaneous streaming: PASSED
  - Disconnection resilience (one client disconnects, remaining client continues): PASSED
  - ConnectionManager broadcast & connection tracking: PASSED

---

## 7. Manual Verification

1. **REST Endpoints**:
   - `GET /` → `200 OK` (`{"system": "SIH-NAVIS", "status": "online", "version": "0.1.0"}`)
   - `GET /health` → `200 OK` (`{"status": "healthy"}`)
   - `GET /telemetry` → `200 OK` (validated Pydantic `Telemetry` object)
   - `GET /docs` → `200 OK` (Swagger UI HTML)
   - `GET /redoc` → `200 OK` (ReDoc documentation HTML)
2. **WebSocket Real-Time Stream**:
   - Verified continuous JSON packets streamed at 10 Hz.
   - Verified timestamps and coordinates update dynamically over time.
   - Connected 2 simultaneous clients and verified both received independent, synchronized streams.
   - Verified clean disconnection and cleanup in `ConnectionManager`.

---

## 8. Issues Encountered

None.

---

## 9. Future Integration

The architecture built in Milestone 2 provides plug points for upcoming subsystems:
- **Unreal Engine / AirSim**: Will interface through an ingestion adapter feeding `TelemetryService`.
- **INS & Visual SLAM / ML**: Telemetry estimates from navigation modules will replace `MockTelemetryGenerator` without breaking the WebSocket contract.
- **Next.js Frontend (Milestone 3+)**: The UI will connect to `/ws/telemetry` to power real-time 3D flight paths, attitude indicators (roll/pitch/yaw), velocity gauges, and GPS-denied confidence meters.

---

## 10. Milestone Status

**MILESTONE 2 STATUS: COMPLETE**
