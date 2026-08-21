"""Trajectory repository with in-memory fast ring buffer and SQLite persistence."""

from collections import deque
from datetime import datetime, timezone
import logging
import math
from typing import Any

from app.config import settings
from app.database.db import get_connection
from app.schemas.trajectory import TrajectoryPoint, TrajectoryResponse, TrajectorySyncPair

logger = logging.getLogger("sih_navis.repository.trajectory")


class TrajectoryRepository:
    """Stores and retrieves ground truth and estimated pose trajectory points."""

    def __init__(self, max_points: int = settings.MAX_TRAJECTORY_POINTS):
        self.max_points = max_points
        self._gt_buffer: deque[TrajectoryPoint] = deque(maxlen=max_points)
        self._est_buffer: deque[TrajectoryPoint] = deque(maxlen=max_points)
        self._sync_pairs: deque[TrajectorySyncPair] = deque(maxlen=max_points)

    def record_ground_truth(self, pt: TrajectoryPoint, mission_id: str | None = None) -> None:
        """Store ground truth trajectory sample."""
        self._gt_buffer.append(pt)
        self._match_and_persist(pt, is_gt=True, mission_id=mission_id)

    def record_estimated(self, pt: TrajectoryPoint, mission_id: str | None = None) -> None:
        """Store estimated pose trajectory sample."""
        self._est_buffer.append(pt)
        self._match_and_persist(pt, is_gt=False, mission_id=mission_id)

    def _match_and_persist(self, pt: TrajectoryPoint, is_gt: bool, mission_id: str | None) -> None:
        """Pair up corresponding frame_id points in memory buffer."""
        # Check if corresponding sample exists in pairs
        target_pair = None
        for pair in reversed(self._sync_pairs):
            if pair.frame_id == pt.frame_id:
                target_pair = pair
                break

        if target_pair is None:
            target_pair = TrajectorySyncPair(frame_id=pt.frame_id, timestamp=pt.timestamp)
            self._sync_pairs.append(target_pair)

        if is_gt:
            target_pair.ground_truth = pt
        else:
            target_pair.estimated = pt

        if target_pair.ground_truth is not None and target_pair.estimated is not None:
            dx = target_pair.estimated.x - target_pair.ground_truth.x
            dy = target_pair.estimated.y - target_pair.ground_truth.y
            dz = target_pair.estimated.z - target_pair.ground_truth.z
            target_pair.error_3d = math.sqrt(dx * dx + dy * dy + dz * dz)

    def get_trajectory(
        self, limit: int = 500, mission_id: str | None = None
    ) -> TrajectoryResponse:
        """Return synchronized trajectory points up to limit."""
        gt_list = sorted(self._gt_buffer, key=lambda p: (p.frame_id or 0, p.timestamp))[-limit:]
        est_list = sorted(self._est_buffer, key=lambda p: (p.frame_id or 0, p.timestamp))[-limit:]
        return TrajectoryResponse(
            mission_id=mission_id,
            ground_truth=gt_list,
            estimated=est_list,
            sample_count=min(len(gt_list), len(est_list)),
        )

    def get_synchronized_pairs(self, limit: int = 500) -> list[TrajectorySyncPair]:
        """Return matched synchronized pairs having both GT and EST sorted chronologically."""
        valid_pairs = [p for p in self._sync_pairs if p.ground_truth is not None and p.estimated is not None]
        sorted_pairs = sorted(valid_pairs, key=lambda p: (p.frame_id or 0, p.timestamp or 0.0))
        return sorted_pairs[-limit:]

    def clear(self) -> None:
        """Reset trajectory buffers."""
        self._gt_buffer.clear()
        self._est_buffer.clear()
        self._sync_pairs.clear()
        logger.info("Trajectory buffers cleared.")


trajectory_repository = TrajectoryRepository()
