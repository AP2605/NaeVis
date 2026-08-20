"""P2 Simulation Ground Truth service handler."""

import logging
from app.schemas.integrated import IntegratedFrame
from app.schemas.p2 import SimulationGroundTruthPacket
from app.services.integration_service import integration_service

logger = logging.getLogger("sih_navis.p2.service")


class P2Service:
    """Service layer handling P2 simulation ground truth ingestion and processing."""

    async def process_ground_truth_packet(self, packet: SimulationGroundTruthPacket) -> IntegratedFrame:
        """Validate, synchronize, and broadcast incoming P2 ground truth."""
        logger.debug("Processing P2 ground truth packet for timestamp %.3f", packet.timestamp)
        return await integration_service.ingest_p2(packet)


p2_service = P2Service()
