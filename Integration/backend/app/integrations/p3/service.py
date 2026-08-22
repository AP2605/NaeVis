import logging
from typing import Any
from app.integrations.p3.adapter import normalize_p3_navigation
from app.schemas.integrated import IntegratedFrame
from app.schemas.p3 import NavigationStatePacket
from app.services.integration_service import integration_service

logger = logging.getLogger("sih_navis.p3.service")


class P3Service:
    """Service layer handling P3 navigation state ingestion and processing."""

    async def process_navigation_packet(
        self, packet: NavigationStatePacket | dict[str, Any], is_real: bool = False
    ) -> IntegratedFrame:
        """Validate, normalize, synchronize, and broadcast incoming P3 navigation state."""
        normalized = normalize_p3_navigation(packet, is_real=is_real)
        logger.debug("Processing P3 packet for frame %d", normalized.frame_id)
        return await integration_service.ingest_p3(normalized, is_real=is_real)


p3_service = P3Service()
