"""Central Integration Service Layer.

Orchestrates P1, P2, and P3 ingestion, maintains unified state synchronization,
and facilitates real-time broadcasting to frontend clients.
"""

from datetime import datetime, timezone
import logging
import math
from typing import Any

from app.schemas.integrated import IntegratedFrame, IntegratedState
from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket
from app.schemas.telemetry import Telemetry
from app.schemas.websocket import (
    GroundTruthEvent,
    IntegratedStateEvent,
    NavigationEvent,
    PerceptionEvent,
)
from app.services.frame_sync import frame_synchronizer
from app.services.telemetry_service import telemetry_service
from app.websocket.manager import connection_manager

logger = logging.getLogger("sih_navis.integration")


class IntegrationService:
    """Hub coordinating data ingestion, state integration, and client broadcasting."""

    def __init__(self):
        self.sync = frame_synchronizer

    async def ingest_p1(self, packet: P1VisionResult) -> IntegratedFrame:
        """Ingest P1 perception packet, update synchronizer, and broadcast."""
        frame = self.sync.ingest_p1(packet)
        # Broadcast perception event to WebSocket clients
        event = PerceptionEvent(data=packet)
        await connection_manager.broadcast_json(event)
        # Also broadcast integrated state summary
        state = self.sync.get_latest_integrated_state()
        await connection_manager.broadcast_json(IntegratedStateEvent(data=state))
        return frame

    async def ingest_p2(self, packet: SimulationGroundTruthPacket) -> IntegratedFrame:
        """Ingest P2 ground truth packet, update synchronizer, and broadcast."""
        frame = self.sync.ingest_p2(packet)
        # Broadcast ground truth event to WebSocket clients
        event = GroundTruthEvent(data=packet)
        await connection_manager.broadcast_json(event)
        # Broadcast integrated state update
        state = self.sync.get_latest_integrated_state()
        await connection_manager.broadcast_json(IntegratedStateEvent(data=state))
        return frame

    async def ingest_p3(self, packet: NavigationStatePacket) -> IntegratedFrame:
        """Ingest P3 navigation state packet, update synchronizer, and broadcast."""
        frame = self.sync.ingest_p3(packet)
        # Broadcast navigation event to WebSocket clients
        event = NavigationEvent(data=packet)
        await connection_manager.broadcast_json(event)
        # Broadcast integrated state update
        state = self.sync.get_latest_integrated_state()
        await connection_manager.broadcast_json(IntegratedStateEvent(data=state))
        return frame

    def get_current_integrated_state(self) -> IntegratedState:
        """Get the current unified integrated state."""
        return self.sync.get_latest_integrated_state()

    def get_current_telemetry(self) -> Telemetry:
        """Return drone telemetry.

        If active P3 navigation packets exist, returns telemetry derived from P3.
        Otherwise, falls back to the M1/M2 TelemetryService generator.
        """
        latest_p3 = self.sync._latest_p3
        if latest_p3 is not None:
            # Derive scalar velocity from 3D velocity vector
            vel_mag = math.sqrt(
                latest_p3.velocity.x**2 + latest_p3.velocity.y**2 + latest_p3.velocity.z**2
            )
            return Telemetry(
                x=round(latest_p3.estimated_pose.x, 3),
                y=round(latest_p3.estimated_pose.y, 3),
                z=round(latest_p3.estimated_pose.z, 3),
                velocity=round(vel_mag, 2),
                roll=round(latest_p3.estimated_pose.roll, 2),
                pitch=round(latest_p3.estimated_pose.pitch, 2),
                yaw=round(latest_p3.estimated_pose.yaw, 2),
                confidence=round(latest_p3.confidence, 2),
                timestamp=datetime.now(timezone.utc),
            )

        # Fallback to default telemetry service
        return telemetry_service.get_current_telemetry()


# Global singleton instance
integration_service = IntegrationService()
