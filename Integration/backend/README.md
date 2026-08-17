# SIH-NAVIS — P4 Backend (Milestones 1 & 2)

Backend service for the **SIH-NAVIS** GPS-denied autonomous drone navigation simulation system. It provides real-time telemetry streaming over WebSockets, REST API endpoints, mock simulation data generation, and module integration abstraction.

---

## 1. Prerequisites

- Python 3.10+ (Python 3.12 recommended)
- `pip`

---

## 2. Virtual Environment Setup

From the `Integration/backend` directory:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Windows (Command Prompt):
.\venv\Scripts\activate.bat
# On Linux / macOS:
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Running the Server

Start the FastAPI application with Uvicorn:

```bash
uvicorn app.main:app --reload --port 8000
```

---

## 5. Endpoints & Real-Time Communication

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root system info and status check |
| `GET` | `/health` | Health check probe (`{"status": "healthy"}`) |
| `GET` | `/telemetry` | Current estimated drone pose and telemetry |

### WebSocket Endpoint

| Protocol | Path | Description |
|---|---|---|
| `WS` | `/ws/telemetry` | Continuous real-time telemetry stream (10 Hz by default) |

#### WebSocket Event Format

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

---

## 6. Configuration

Settings are managed in `app/config.py` with environment variable overrides:

| Variable | Default | Description |
|---|---|---|
| `TELEMETRY_STREAM_INTERVAL` | `0.1` | Stream interval in seconds (0.1s = 100ms = 10 Hz) |
| `LOG_LEVEL` | `INFO` | Application log level |

---

## 7. Interactive API Documentation

Once the server is running:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 8. Running Tests

Execute the complete test suite with `pytest`:

```bash
pytest -v
```
