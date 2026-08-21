"""Mock P3 Navigation Mission Receiver Server.

Lightweight HTTP server on port 8003 that simulates the P3 Navigation Module's
mission reception endpoint: POST /api/v1/mission
Returns HTTP 200 with status: ACCEPTED.
"""

import uvicorn
from fastapi import FastAPI, Request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Mock P3 Server] %(message)s")
logger = logging.getLogger("mock_p3_server")

app = FastAPI(title="Mock P3 Navigation Engine")


@app.post("/api/v1/mission")
async def receive_mission(request: Request):
    """Receive and acknowledge validated mission from P4 integration backend."""
    data = await request.json()
    mission_id = data.get("mission_id", "unknown")
    name = data.get("mission_name", "unnamed")
    waypoints = data.get("waypoints", [])
    logger.info("Received mission '%s' (%s) with %d waypoints", name, mission_id, len(waypoints))
    return {
        "status": "ACCEPTED",
        "mission_id": mission_id,
        "message": f"Mission '{name}' accepted by P3 navigation engine for execution.",
    }


@app.get("/health")
def health():
    return {"status": "online", "module": "Mock P3 Navigation"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
