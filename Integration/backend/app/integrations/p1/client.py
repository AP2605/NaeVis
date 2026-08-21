"""P1 Perception external client adapter."""

import logging
import httpx
from app.config import settings
from app.schemas.p1 import P1VisionResult

logger = logging.getLogger("sih_navis.p1.client")


class P1Client:
    """Async HTTP client to interact with external P1 perception service if needed."""

    def __init__(self, base_url: str = settings.P1_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def fetch_latest_perception(self) -> P1VisionResult | None:
        """Fetch latest perception result from P1 REST endpoint."""
        url = f"{self.base_url}/api/v1/perception/latest"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return P1VisionResult.model_validate(response.json())
                logger.warning("P1 endpoint returned HTTP %d: %s", response.status_code, response.text)
        except Exception as exc:
            logger.debug("Failed to fetch from P1 service at %s: %s", url, exc)
        return None


p1_client = P1Client()
