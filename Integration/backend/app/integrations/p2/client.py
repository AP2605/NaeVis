"""P2 Simulation external client adapter."""

import logging
import httpx
from app.config import settings
from app.schemas.p2 import SimulationGroundTruthPacket

logger = logging.getLogger("sih_navis.p2.client")


class P2Client:
    """Async HTTP client to interact with external P2 simulation service if needed."""

    def __init__(self, base_url: str = settings.P2_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def fetch_latest_ground_truth(self) -> SimulationGroundTruthPacket | None:
        """Fetch latest ground truth packet from P2 simulation service."""
        url = f"{self.base_url}/api/v1/simulation/ground-truth/latest"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return SimulationGroundTruthPacket.model_validate(response.json())
                logger.warning("P2 endpoint returned HTTP %d: %s", response.status_code, response.text)
        except Exception as exc:
            logger.debug("Failed to fetch from P2 service at %s: %s", url, exc)
        return None


p2_client = P2Client()
