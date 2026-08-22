"""Frame Synchronization Service.

Associates and aligns asynchronous packets from P1 (Perception), P2 (Simulation Ground Truth),
and P3 (Navigation) using frame_id as primary key and timestamp as secondary reference.
Provides detailed source health metrics, stale detection, and multi-producer diagnostics.
"""

from collections import OrderedDict
import logging
import time
from typing import Any

from app.config import settings
from app.schemas.integrated import IntegratedFrame, IntegratedState, SourceHealth
from app.schemas.p1 import P1VisionResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket
from app.services.camera_service import camera_service

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

        # M6 Source Health and Real Module Origin Tracking
        self._p1_is_real: bool = False
        self._p2_is_real: bool = False
        self._p3_is_real: bool = False

        # Periodic logging tracking
        self._p1_last_log_time: float = 0.0
        self._p2_last_log_time: float = 0.0
        self._p3_last_log_time: float = 0.0

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

    def ingest_p1(self, packet: P1VisionResult, is_real: bool = False) -> IntegratedFrame:
        """Ingest and synchronize P1 perception packet."""
        now = time.time()
        if self._last_p1_time > 0:
            dt = now - self._last_p1_time
            if dt > 0:
                self._p1_fps = 0.9 * self._p1_fps + 0.1 * (1.0 / dt)
        self._last_p1_time = now
        self._p1_count += 1
        self._latest_p1 = packet
        if is_real:
            self._p1_is_real = True

        frame = self._get_or_create_frame(packet.frame_id, packet.timestamp)
        frame.perception = packet
        if "p1" not in frame.sync_sources:
            frame.sync_sources.append("p1")

        # Periodic summary logging
        if (now - self._p1_last_log_time >= 5.0) or (self._p1_count % 20 == 0):
            src_tag = "REAL" if self._p1_is_real else "MOCK"
            logger.info(
                "[P1 Perception] Ingested packet [%s] | frame=%d | terrain=%s | landmarks=%d | rate=%.1f Hz",
                src_tag,
                packet.frame_id,
                packet.terrain.terrain_type,
                len(packet.landmarks),
                self._p1_fps,
            )
            self._p1_last_log_time = now

        return frame

    def ingest_p2(self, packet: SimulationGroundTruthPacket, is_real: bool = False) -> IntegratedFrame:
        """Ingest and synchronize P2 simulation ground truth packet."""
        now = time.time()
        if self._last_p2_time > 0:
            dt = now - self._last_p2_time
            if dt > 0:
                self._p2_fps = 0.9 * self._p2_fps + 0.1 * (1.0 / dt)
        self._last_p2_time = now
        self._p2_count += 1
        self._latest_p2 = packet
        if is_real:
            self._p2_is_real = True

        frame_id = packet.frame_id if packet.frame_id is not None else self._p2_count
        frame = self._get_or_create_frame(frame_id, packet.timestamp)
        frame.ground_truth = packet
        if packet.camera is not None and packet.camera.image_path:
            frame.camera_available = True
        if "p2" not in frame.sync_sources:
            frame.sync_sources.append("p2")

        # Periodic summary logging
        if (now - self._p2_last_log_time >= 5.0) or (self._p2_count % 50 == 0):
            src_tag = "REAL" if self._p2_is_real else "MOCK"
            logger.info(
                "[P2 GroundTruth] Ingested packet [%s] | frame=%d | pos=(%.2f, %.2f, %.2f) | rate=%.1f Hz",
                src_tag,
                frame_id,
                packet.position.x,
                packet.position.y,
                packet.position.z,
                self._p2_fps,
            )
            self._p2_last_log_time = now

        return frame

    def ingest_p3(self, packet: NavigationStatePacket, is_real: bool = False) -> IntegratedFrame:
        """Ingest and synchronize P3 navigation state packet."""
        now = time.time()
        if self._last_p3_time > 0:
            dt = now - self._last_p3_time
            if dt > 0:
                self._p3_fps = 0.9 * self._p3_fps + 0.1 * (1.0 / dt)
        self._last_p3_time = now
        self._p3_count += 1
        self._latest_p3 = packet
        if is_real:
            self._p3_is_real = True

        frame = self._get_or_create_frame(packet.frame_id, packet.timestamp)
        frame.navigation = packet
        if "p3" not in frame.sync_sources:
            frame.sync_sources.append("p3")

        # Periodic summary logging
        if (now - self._p3_last_log_time >= 5.0) or (self._p3_count % 50 == 0):
            src_tag = "REAL" if self._p3_is_real else "MOCK"
            logger.info(
                "[P3 Navigation] Ingested packet [%s] | frame=%d | state=%s | conf=%.2f | rate=%.1f Hz",
                src_tag,
                packet.frame_id,
                packet.tracking_state,
                packet.confidence,
                self._p3_fps,
            )
            self._p3_last_log_time = now

        return frame

    def get_frame(self, frame_id: int) -> IntegratedFrame | None:
        """Retrieve integrated frame by frame_id."""
        return self._frames.get(frame_id)

    def get_recent_frames(self, limit: int = 50) -> list[IntegratedFrame]:
        """Retrieve most recent integrated frames in chronological order."""
        sorted_frames = sorted(self._frames.values(), key=lambda f: f.frame_id)
        return sorted_frames[-limit:]

    def get_source_health(self) -> dict[str, Any]:
        """Compute detailed health and stale detection for all data sources."""
        now = time.time()
        stale_threshold = settings.STALE_TIMEOUT_SEC

        def _calc_status(last_time: float, count: int, is_real: bool, fps: float, last_fid: int | None):
            age = (now - last_time) if last_time > 0 else None
            if count == 0 or last_time == 0:
                state = "DISCONNECTED"
            elif age is not None and age <= stale_threshold:
                state = "CONNECTED" if is_real else "MOCK"
            else:
                state = "STALE"

            return {
                "state": state,
                "is_real": is_real,
                "last_packet_time": round(last_time, 3),
                "packet_count": count,
                "rate_hz": round(fps, 1),
                "last_frame_id": last_fid,
                "age_seconds": round(age, 2) if age is not None else None,
            }

        p1_fid = self._latest_p1.frame_id if self._latest_p1 else None
        p2_fid = self._latest_p2.frame_id if self._latest_p2 else None
        p3_fid = self._latest_p3.frame_id if self._latest_p3 else None

        return {
            "p1": _calc_status(self._last_p1_time, self._p1_count, self._p1_is_real, self._p1_fps, p1_fid),
            "p2": _calc_status(self._last_p2_time, self._p2_count, self._p2_is_real, self._p2_fps, p2_fid),
            "p3": _calc_status(self._last_p3_time, self._p3_count, self._p3_is_real, self._p3_fps, p3_fid),
            "camera": camera_service.get_health(),
        }

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

        source_health = self.get_source_health()

        system_status: dict[str, Any] = {
            "p1_active": source_health["p1"]["state"] in ("CONNECTED", "MOCK"),
            "p2_active": source_health["p2"]["state"] in ("CONNECTED", "MOCK"),
            "p3_active": source_health["p3"]["state"] in ("CONNECTED", "MOCK"),
            "camera_active": source_health["camera"]["state"] in ("CONNECTED", "MOCK"),
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
            source_health=source_health,
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
        self._p1_is_real = False
        self._p2_is_real = False
        self._p3_is_real = False
        self._p1_last_log_time = 0.0
        self._p2_last_log_time = 0.0
        self._p3_last_log_time = 0.0
        logger.info("Frame synchronizer state reset.")


# Global singleton instance
frame_synchronizer = FrameSynchronizer()
