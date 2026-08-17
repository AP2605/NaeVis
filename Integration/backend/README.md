# SIH-NAVIS — P4 Backend (Milestone 1)

Backend service for the **SIH-NAVIS** GPS-denied autonomous drone navigation simulation system. It provides telemetry ingestion, mock simulation generators, and REST API endpoints for downstream frontend visualization and module integration.

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

## 5. Available Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root system info and status check |
| `GET` | `/health` | Health check probe (`{"status": "healthy"}`) |
| `GET` | `/telemetry` | Current estimated drone pose and telemetry |

---

## 6. Interactive API Documentation

Once the server is running, explore and test the endpoints interactively:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 7. Running Tests

Run the test suite with `pytest`:

```bash
pytest
```
