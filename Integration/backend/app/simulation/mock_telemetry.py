"""Mock telemetry generator for simulation and testing."""

from datetime import datetime, timezone
import math
import random
import time

from app.schemas.telemetry import Telemetry


class MockTelemetryGenerator:
    """Generates realistic-looking mock drone telemetry.

    Simulates a drone navigating in a 3D coordinate space with continuous
    position evolution, subtle orientation adjustments, velocity variations,
    and high localization confidence.
    """

    def __init__(
        self,
        base_x: float = 0.0,
        base_y: float = 0.0,
        base_z: float = 10.0,
        speed: float = 2.5,
    ):
        self.x = base_x
        self.y = base_y
        self.z = base_z
        self.speed = speed
        self.start_time = time.time()

    def generate(self) -> Telemetry:
        """Generate the next telemetry data point."""
        elapsed = time.time() - self.start_time

        # Smooth flight path simulation with small random noise
        # Circular / figure-8 pattern with altitude oscillation
        radius = 15.0
        angular_speed = 0.2

        current_x = self.x + radius * math.sin(elapsed * angular_speed) + random.uniform(-0.15, 0.15)
        current_y = self.y + radius * math.sin(elapsed * angular_speed * 2) * 0.5 + random.uniform(-0.15, 0.15)
        current_z = self.z + 2.0 * math.sin(elapsed * 0.1) + random.uniform(-0.05, 0.05)

        # Dynamic velocity with slight noise
        velocity = max(0.0, round(self.speed + random.uniform(-0.3, 0.3), 2))

        # Dynamic attitude (roll, pitch, yaw) in degrees
        roll = round(math.sin(elapsed * 0.5) * 3.0 + random.uniform(-0.5, 0.5), 2)
        pitch = round(math.cos(elapsed * 0.5) * 2.5 + random.uniform(-0.5, 0.5), 2)
        yaw = round((math.degrees(elapsed * angular_speed) + random.uniform(-1.0, 1.0)) % 360.0, 2)

        # Confidence typically high for GPS-denied SLAM/INS in nominal flight (0.85 - 0.99)
        confidence = round(random.uniform(0.88, 0.98), 2)

        return Telemetry(
            x=round(current_x, 3),
            y=round(current_y, 3),
            z=round(current_z, 3),
            velocity=velocity,
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )
