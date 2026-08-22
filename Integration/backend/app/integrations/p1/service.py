import logging
from typing import Any
from app.integrations.p1.adapter import normalize_p1_payload
from app.schemas.integrated import IntegratedFrame
from app.schemas.p1 import P1VisionResult
from app.services.integration_service import integration_service

logger = logging.getLogger("sih_navis.p1.service")


class P1Service:
    """Service layer handling P1 perception data ingestion and processing."""

    async def process_perception_packet(
        self, packet: P1VisionResult | dict[str, Any], is_real: bool = False
    ) -> IntegratedFrame:
        """Validate, normalize, synchronize, and broadcast incoming P1 vision result."""
        normalized = normalize_p1_payload(packet, is_real=is_real)
        logger.debug("Processing P1 packet for frame %d", normalized.frame_id)
        return await integration_service.ingest_p1(normalized, is_real=is_real)


p1_service = P1Service()
