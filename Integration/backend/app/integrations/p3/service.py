"""P3 Navigation service handler."""

import logging
from app.schemas.integrated import IntegratedFrame
from app.schemas.p3 import NavigationStatePacket
from app.services.integration_service import integration_service

logger = logging.getLogger("sih_navis.p3.service")


class P3Service:
    """Service layer handling P3 navigation state ingestion and processing."""

    async def process_navigation_packet(self, packet: NavigationStatePacket) -> IntegratedFrame:
        """Validate, synchronize, and broadcast incoming P3 navigation state."""
        logger.debug("Processing P3 packet for frame %d", packet.frame_id)
        return await integration_service.ingest_p3(packet)


p3_service = P3Service()
