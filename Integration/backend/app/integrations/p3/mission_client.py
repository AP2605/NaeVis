"""P3 Navigation System Mission Client Adapter.

Transmits validated mission definitions to the P3 Navigation module via HTTP REST.
Handles acknowledgements (ACCEPTED, REJECTED, INVALID, BUSY) and connection states cleanly.
"""

import logging
from typing import Any
import httpx

from app.config import settings
from app.schemas.mission import MissionResponse

logger = logging.getLogger("sih_navis.integrations.p3.mission")


class P3MissionClient:
    """HTTP Client communicating mission payloads to P3 Navigation service."""

    def __init__(self, base_url: str = settings.P3_BASE_URL, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def send_mission(self, mission: MissionResponse) -> dict[str, Any]:
        """Transmit mission payload to P3 navigation service."""
        payload = {
            "mission_id": mission.mission_id,
            "mission_name": mission.mission_name,
            "source": {
                "x": mission.source.x,
                "y": mission.source.y,
                "z": mission.source.z,
            },
            "waypoints": [
                {
                    "x": wp.x,
                    "y": wp.y,
                    "z": wp.z,
                    "index": wp.waypoint_index,
                    "name": wp.name,
                }
                for wp in mission.waypoints
            ],
            "destination": {
                "x": mission.destination.x,
                "y": mission.destination.y,
                "z": mission.destination.z,
            },
            "coordinate_frame": mission.coordinate_frame,
        }

        endpoint = f"{self.base_url}/api/v1/mission"
        logger.info("Sending mission %s to P3 at %s", mission.mission_id, endpoint)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)
                if response.status_code in (200, 201, 202):
                    data = response.json()
                    status = data.get("status", "ACCEPTED")
                    logger.info("P3 response for mission %s: %s", mission.mission_id, status)
                    return {"success": True, "status": status, "response": data}
                elif response.status_code == 400:
                    logger.warning("P3 rejected mission %s as INVALID: %s", mission.mission_id, response.text)
                    return {"success": False, "status": "INVALID", "error": response.text}
                elif response.status_code == 409:
                    logger.warning("P3 is BUSY with another mission: %s", response.text)
                    return {"success": False, "status": "BUSY", "error": response.text}
                else:
                    logger.warning("P3 returned HTTP %d for mission %s", response.status_code, mission.mission_id)
                    return {
                        "success": False,
                        "status": "REJECTED",
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }
        except httpx.ConnectError:
            logger.info("P3 service offline at %s (Mock/Pending integration mode active)", endpoint)
            return {
                "success": False,
                "status": "UNAVAILABLE",
                "message": f"P3 navigation endpoint unreachable at {endpoint}. Mock receiver can be used for demonstration.",
            }
        except httpx.TimeoutException:
            logger.warning("P3 service timed out at %s", endpoint)
            return {
                "success": False,
                "status": "TIMEOUT",
                "message": "P3 service timed out while receiving mission",
            }
        except Exception as exc:
            logger.error("Unexpected error transmitting mission to P3: %s", exc)
            return {
                "success": False,
                "status": "ERROR",
                "error": str(exc),
            }


p3_mission_client = P3MissionClient()
