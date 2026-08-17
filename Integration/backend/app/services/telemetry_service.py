"""Telemetry service layer."""

from app.schemas.telemetry import Telemetry
from app.simulation.mock_telemetry import MockTelemetryGenerator


class TelemetryService:
    """Service to handle telemetry acquisition and processing.

    Currently uses MockTelemetryGenerator, but provides an abstraction
    layer that can later be swapped for real AirSim/Unreal SLAM/INS feeds.
    """

    def __init__(self, generator: MockTelemetryGenerator | None = None):
        self._generator = generator or MockTelemetryGenerator()

    def get_current_telemetry(self) -> Telemetry:
        """Fetch current telemetry data."""
        return self._generator.generate()


# Global singleton instance for easy dependency injection
telemetry_service = TelemetryService()
