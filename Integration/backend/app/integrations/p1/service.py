"""P1 Perception service handler."""

import logging
from app.schemas.integrated import IntegratedFrame
from app.schemas.p1 import P1VisionResult
from app.services.integration_service import integration_service

logger = logging.getLogger("sih_navis.p1.service")


class P1Service:
    """Service layer handling P1 perception data ingestion and processing."""

    async def process_perception_packet(self, packet: P1VisionResult) -> IntegratedFrame:
        """Validate, synchronize, and broadcast incoming P1 vision result."""
        logger.debug("Processing P1 packet for frame %d", packet.frame_id)
        return await integration_service.ingest_p1(packet)


p1_service = P1Service()
