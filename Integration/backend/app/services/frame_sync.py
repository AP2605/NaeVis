"""Frame Synchronization Service.

Associates and aligns asynchronous packets from P1 (Perception), P2 (Simulation Ground Truth),
and P3 (Navigation) using frame_id as primary key and timestamp as secondary reference.
"""

from collections import OrderedDict
import logging
import time
from typing import Any

from app.config import settings
from app.schemas.integrated import IntegratedFrame, IntegratedState
from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket

logger = logging.getLogger("sih_navis.sync")


class FrameSynchronizer:
    """Synchronizes multi-rate data streams by frame_id and timestamp."""

    def __init__(self, max_buffer_size: int = settings.FRAME_SYNC_BUFFER_SIZE):
        self.max_buffer_size = max_buffer_size
        self._frames: OrderedDict[int, IntegratedFrame] = OrderedDict()
        
        # Latest received packets for instant state retrieval
        self._latest_p1: P1VisionResult | None = None
        self._latest_p2: SimulationGroundTruthPacket | None = None
        self._latest_p3: NavigationStatePacket | None = None

        # Tracking metrics
        self._p1_count: int = 0
        self._p2_count: int = 0
        self._p3_count: int = 0
        self._last_p1_time: float = 0.0
        self._last_p2_time: float = 0.0
        self._last_p3_time: float = 0.0
        self._p1_fps: float = 0.0
        self._p2_fps: float = 0.0
        self._p3_fps: float = 0.0

    def _get_or_create_frame(self, frame_id: int, timestamp: float) -> IntegratedFrame:
        """Retrieve existing frame container or initialize a new one in the buffer."""
        if frame_id in self._frames:
            frame = self._frames[frame_id]
            # Update timestamp if original was placeholder
            if timestamp > 0 and frame.timestamp == 0:
                frame.timestamp = timestamp
            return frame

        # Evict oldest if buffer limit exceeded
        while len(self._frames) >= self.max_buffer_size:
            self._frames.popitem(last=False)

        frame = IntegratedFrame(
            frame_id=frame_id,
            timestamp=timestamp,
            created_at=time.time(),
        )
        self._frames[frame_id] = frame
        return frame

    def ingest_p1(self, packet: P1VisionResult) -> IntegratedFrame:
        """Ingest and synchronize P1 perception packet."""
        now = time.time()
        if self._last_p1_time > 0:
            dt = now - self._last_p1_time
            if dt > 0:
                self._p1_fps = 0.9 * self._p1_fps + 0.1 * (1.0 / dt)
        self._last_p1_time = now
        self._p1_count += 1
        self._latest_p1 = packet

        frame = self._get_or_create_frame(packet.frame_id, packet.timestamp)
        frame.perception = packet
        if "p1" not in frame.sync_sources:
            frame.sync_sources.append("p1")

        logger.info(
            "[P1] Perception packet received | frame=%d | terrain=%s | landmarks=%d",
            packet.frame_id,
            packet.terrain.terrain_type,
            len(packet.landmarks),
        )
        return frame

    def ingest_p2(self, packet: SimulationGroundTruthPacket) -> IntegratedFrame:
        """Ingest and synchronize P2 simulation ground truth packet."""
        now = time.time()
        if self._last_p2_time > 0:
            dt = now - self._last_p2_time
            if dt > 0:
                self._p2_fps = 0.9 * self._p2_fps + 0.1 * (1.0 / dt)
        self._last_p2_time = now
        self._p2_count += 1
        self._latest_p2 = packet

        frame_id = packet.frame_id if packet.frame_id is not None else self._p2_count
        frame = self._get_or_create_frame(frame_id, packet.timestamp)
        frame.ground_truth = packet
        if packet.camera is not None and packet.camera.image_path:
            frame.camera_available = True
        if "p2" not in frame.sync_sources:
            frame.sync_sources.append("p2")

        logger.info(
            "[P2] Ground truth packet received | frame=%d | pos=(%.2f, %.2f, %.2f)",
            frame_id,
            packet.position.x,
            packet.position.y,
            packet.position.z,
        )
        return frame

    def ingest_p3(self, packet: NavigationStatePacket) -> IntegratedFrame:
        """Ingest and synchronize P3 navigation state packet."""
        now = time.time()
        if self._last_p3_time > 0:
            dt = now - self._last_p3_time
            if dt > 0:
                self._p3_fps = 0.9 * self._p3_fps + 0.1 * (1.0 / dt)
        self._last_p3_time = now
        self._p3_count += 1
        self._latest_p3 = packet

        frame = self._get_or_create_frame(packet.frame_id, packet.timestamp)
        frame.navigation = packet
        if "p3" not in frame.sync_sources:
            frame.sync_sources.append("p3")

        logger.info(
            "[P3] Navigation packet received | frame=%d | state=%s | conf=%.2f",
            packet.frame_id,
            packet.tracking_state,
            packet.confidence,
        )
        return frame

    def get_frame(self, frame_id: int) -> IntegratedFrame | None:
        """Retrieve integrated frame by frame_id."""
        return self._frames.get(frame_id)

    def get_recent_frames(self, limit: int = 50) -> list[IntegratedFrame]:
        """Retrieve most recent integrated frames in chronological order."""
        values = list(self._frames.values())
        return values[-limit:]

    def get_latest_integrated_state(self) -> IntegratedState:
        """Construct the latest composite state across all modules."""
        # Find highest frame_id
        highest_frame_id: int | None = None
        latest_ts: float | None = None

        if self._latest_p3 is not None:
            highest_frame_id = self._latest_p3.frame_id
            latest_ts = self._latest_p3.timestamp
        elif self._latest_p2 is not None and self._latest_p2.frame_id is not None:
            highest_frame_id = self._latest_p2.frame_id
            latest_ts = self._latest_p2.timestamp
        elif self._latest_p1 is not None:
            highest_frame_id = self._latest_p1.frame_id
            latest_ts = self._latest_p1.timestamp

        # Check latest camera reference from P2
        camera_ref = self._latest_p2.camera if self._latest_p2 else None

        sync_status: dict[str, Any] = {
            "buffered_frames": len(self._frames),
            "p1_packets_total": self._p1_count,
            "p2_packets_total": self._p2_count,
            "p3_packets_total": self._p3_count,
            "p1_rate_hz": round(self._p1_fps, 2),
            "p2_rate_hz": round(self._p2_fps, 2),
            "p3_rate_hz": round(self._p3_fps, 2),
        }

        system_status: dict[str, Any] = {
            "p1_active": (time.time() - self._last_p1_time < 3.0) if self._last_p1_time > 0 else False,
            "p2_active": (time.time() - self._last_p2_time < 3.0) if self._last_p2_time > 0 else False,
            "p3_active": (time.time() - self._last_p3_time < 3.0) if self._last_p3_time > 0 else False,
        }

        return IntegratedState(
            current_frame_id=highest_frame_id,
            latest_timestamp=latest_ts,
            ground_truth=self._latest_p2,
            navigation=self._latest_p3,
            perception=self._latest_p1,
            latest_camera=camera_ref,
            sync_status=sync_status,
            system_status=system_status,
        )

    def reset(self) -> None:
        """Clear all buffers and reset tracking counters."""
        self._frames.clear()
        self._latest_p1 = None
        self._latest_p2 = None
        self._latest_p3 = None
        self._p1_count = 0
        self._p2_count = 0
        self._p3_count = 0
        self._last_p1_time = 0.0
        self._last_p2_time = 0.0
        self._last_p3_time = 0.0
        self._p1_fps = 0.0
        self._p2_fps = 0.0
        self._p3_fps = 0.0
        logger.info("Frame synchronizer state reset.")


# Global singleton instance
frame_synchronizer = FrameSynchronizer()
