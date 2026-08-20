"""P3 Navigation external client adapter."""

import logging
import httpx
from app.config import settings
from app.schemas.p3 import NavigationStatePacket

logger = logging.getLogger("sih_navis.p3.client")


class P3Client:
    """Async HTTP client to interact with external P3 navigation service if needed."""

    def __init__(self, base_url: str = settings.P3_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def fetch_latest_navigation_state(self) -> NavigationStatePacket | None:
        """Fetch latest navigation estimation from P3 service."""
        url = f"{self.base_url}/api/v1/navigation/state/latest"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return NavigationStatePacket.model_validate(response.json())
                logger.warning("P3 endpoint returned HTTP %d: %s", response.status_code, response.text)
        except Exception as exc:
            logger.debug("Failed to fetch from P3 service at %s: %s", url, exc)
        return None


p3_client = P3Client()
