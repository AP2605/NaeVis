import logging
from typing import Any
from app.integrations.p2.adapter import normalize_p2_ground_truth
from app.schemas.integrated import IntegratedFrame
from app.schemas.p2 import SimulationGroundTruthPacket
from app.services.integration_service import integration_service

logger = logging.getLogger("sih_navis.p2.service")


class P2Service:
    """Service layer handling P2 simulation ground truth ingestion and processing."""

    async def process_ground_truth_packet(
        self, packet: SimulationGroundTruthPacket | dict[str, Any], is_real: bool = False
    ) -> IntegratedFrame:
        """Validate, normalize, synchronize, and broadcast incoming P2 ground truth."""
        normalized = normalize_p2_ground_truth(packet, is_real=is_real)
        logger.debug("Processing P2 ground truth packet for timestamp %.3f", normalized.timestamp)
        return await integration_service.ingest_p2(normalized, is_real=is_real)


p2_service = P2Service()
