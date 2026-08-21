"""Mission Service layer managing lifecycle, validation, state transitions, and execution progress."""

from datetime import datetime, timezone
import logging
import math
from typing import Any

from app.config import settings
from app.integrations.p3.mission_client import p3_mission_client
from app.repositories.mission_repository import mission_repository
from app.schemas.common import Position3D
from app.schemas.mission import (
    MissionCreate,
    MissionProgress,
    MissionResponse,
    MissionStatus,
    MissionUpdate,
    WaypointResponse,
    WaypointStatus,
)
from app.websocket.manager import connection_manager

logger = logging.getLogger("sih_navis.service.mission")

# Valid state machine transitions
ALLOWED_TRANSITIONS: dict[MissionStatus, set[MissionStatus]] = {
    MissionStatus.DRAFT: {MissionStatus.READY, MissionStatus.ACTIVE, MissionStatus.CANCELLED},
    MissionStatus.READY: {MissionStatus.ACTIVE, MissionStatus.UPLOADING, MissionStatus.DRAFT, MissionStatus.CANCELLED},
    MissionStatus.UPLOADING: {MissionStatus.ACTIVE, MissionStatus.FAILED, MissionStatus.CANCELLED},
    MissionStatus.ACTIVE: {MissionStatus.PAUSED, MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED},
    MissionStatus.PAUSED: {MissionStatus.ACTIVE, MissionStatus.CANCELLED, MissionStatus.FAILED},
    MissionStatus.COMPLETED: set(),  # Terminal
    MissionStatus.FAILED: set(),     # Terminal
    MissionStatus.CANCELLED: set(),  # Terminal
}


class MissionService:
    """Orchestrates mission creation, validation, lifecycle, and progress tracking."""

    def __init__(self):
        self.repo = mission_repository
        self._active_mission_id: str | None = None
        self._active_wp_index: int = 0

    def validate_mission_request(self, req: MissionCreate | MissionUpdate) -> None:
        """Enforce domain rules on mission definitions."""
        if isinstance(req, MissionCreate):
            # Check source and destination are not identical
            dx = req.destination.x - req.source.x
            dy = req.destination.y - req.source.y
            dz = req.destination.z - req.source.z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < 0.1:
                raise ValueError("Destination cannot be identical to source position")

            # Check consecutive waypoints are not duplicates
            all_points = [req.source] + [Position3D(x=w.x, y=w.y, z=w.z) for w in req.waypoints] + [req.destination]
            for i in range(len(all_points) - 1):
                p0, p1 = all_points[i], all_points[i + 1]
                step_dist = math.sqrt((p1.x - p0.x) ** 2 + (p1.y - p0.y) ** 2 + (p1.z - p0.z) ** 2)
                if step_dist < 0.05:
                    raise ValueError(f"Consecutive route points at index {i} and {i+1} are too close / identical (< 0.05m)")

    async def create_mission(self, req: MissionCreate) -> MissionResponse:
        """Validate and create a new mission."""
        self.validate_mission_request(req)
        mission = self.repo.create(req)
        logger.info("Mission created: %s (%s)", mission.mission_name, mission.mission_id)
        
        # Broadcast creation event
        await connection_manager.broadcast_json({
            "event": "mission_status",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "mission_id": mission.mission_id,
                "status": mission.status.value,
                "action": "mission_created",
                "mission": mission.model_dump(),
            },
        })
        return mission

    def get_mission(self, mission_id: str) -> MissionResponse | None:
        """Fetch mission with dynamic progress if currently active."""
        mission = self.repo.get_by_id(mission_id)
        if mission and mission.mission_id == self._active_mission_id:
            mission.progress = self.get_current_progress()
        return mission

    def get_active_mission(self) -> MissionResponse | None:
        """Fetch currently active or most recently updated mission."""
        if self._active_mission_id:
            return self.get_mission(self._active_mission_id)
        missions = self.repo.list_all(limit=1)
        if missions:
            return self.get_mission(missions[0].mission_id)
        return None

    def list_missions(self, limit: int = 50, offset: int = 0) -> list[MissionResponse]:
        """List all stored missions."""
        return self.repo.list_all(limit=limit, offset=offset)

    async def update_mission(self, mission_id: str, req: MissionUpdate) -> MissionResponse:
        """Update an existing mission."""
        existing = self.repo.get_by_id(mission_id)
        if not existing:
            raise KeyError(f"Mission '{mission_id}' not found")

        if existing.status in (MissionStatus.ACTIVE, MissionStatus.COMPLETED):
            raise ValueError(f"Cannot edit mission while in {existing.status.value} state")

        if req.source or req.destination or req.waypoints:
            self.validate_mission_request(req)

        updated = self.repo.update(mission_id, req)
        if not updated:
            raise RuntimeError("Failed to update mission")
        return updated

    async def delete_mission(self, mission_id: str) -> bool:
        """Delete a mission."""
        existing = self.repo.get_by_id(mission_id)
        if not existing:
            raise KeyError(f"Mission '{mission_id}' not found")
        if existing.status == MissionStatus.ACTIVE:
            raise ValueError("Cannot delete an actively running mission. Cancel it first.")
        if self._active_mission_id == mission_id:
            self._active_mission_id = None
        return self.repo.delete(mission_id)

    async def transition_state(self, mission_id: str, new_status: MissionStatus) -> MissionResponse:
        """Safely transition mission state according to state machine rules."""
        mission = self.repo.get_by_id(mission_id)
        if not mission:
            raise KeyError(f"Mission '{mission_id}' not found")

        allowed = ALLOWED_TRANSITIONS.get(mission.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid state transition: Cannot change status from {mission.status.value} to {new_status.value}"
            )

        updated = self.repo.update_status(mission_id, new_status)
        if not updated:
            raise RuntimeError("Failed to update status")

        # Broadcast state change event
        full_mission = self.get_mission(mission_id)
        await connection_manager.broadcast_json({
            "event": "mission_status",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "mission_id": mission_id,
                "status": new_status.value,
                "action": f"mission_{new_status.value.lower()}",
                "mission": full_mission.model_dump() if full_mission else None,
            },
        })
        return updated

    async def start_mission(self, mission_id: str) -> MissionResponse:
        """Transmit mission to P3 and transition to ACTIVE."""
        mission = self.repo.get_by_id(mission_id)
        if not mission:
            raise KeyError(f"Mission '{mission_id}' not found")

        if mission.status not in (MissionStatus.DRAFT, MissionStatus.READY, MissionStatus.PAUSED):
            raise ValueError(f"Cannot start mission currently in {mission.status.value} state")

        # Transmit to P3 Navigation Service
        p3_result = await p3_mission_client.send_mission(mission)
        logger.info("P3 Mission transmission result: %s", p3_result.get("status"))

        # Transition status
        updated = self.repo.update_status(mission_id, MissionStatus.ACTIVE)
        if not updated:
            raise RuntimeError("Failed to set ACTIVE status")

        self._active_mission_id = mission_id
        self._active_wp_index = 0

        # Mark first waypoint CURRENT if waypoints exist
        if updated.waypoints:
            self.repo.update_waypoint_status(mission_id, 0, WaypointStatus.CURRENT)

        active_mission_resp = self.get_mission(mission_id) or updated

        # Broadcast start event
        await connection_manager.broadcast_json({
            "event": "mission_status",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "mission_id": mission_id,
                "status": MissionStatus.ACTIVE.value,
                "action": "mission_started",
                "p3_transmission": p3_result,
                "mission": active_mission_resp.model_dump(),
            },
        })
        return active_mission_resp

    async def pause_mission(self, mission_id: str) -> MissionResponse:
        """Pause currently running mission."""
        return await self.transition_state(mission_id, MissionStatus.PAUSED)

    async def resume_mission(self, mission_id: str) -> MissionResponse:
        """Resume paused mission."""
        return await self.transition_state(mission_id, MissionStatus.ACTIVE)

    async def cancel_mission(self, mission_id: str) -> MissionResponse:
        """Cancel active or paused mission."""
        updated = await self.transition_state(mission_id, MissionStatus.CANCELLED)
        if self._active_mission_id == mission_id:
            self._active_mission_id = None
        return updated

    def get_current_progress(self) -> MissionProgress | None:
        """Calculate progress telemetry for active mission."""
        if not self._active_mission_id:
            return None

        mission = self.repo.get_by_id(self._active_mission_id)
        if not mission:
            return None

        total_wp = len(mission.waypoints)
        completed = sum(1 for w in mission.waypoints if w.status == WaypointStatus.REACHED)
        
        # Calculate percentage (accounting for source->waypoints->destination steps)
        total_legs = total_wp + 1
        current_leg = min(self._active_wp_index, total_legs)
        pct = round((current_leg / total_legs) * 100.0, 1) if total_legs > 0 else 0.0

        return MissionProgress(
            mission_id=mission.mission_id,
            status=mission.status,
            current_waypoint_index=self._active_wp_index,
            total_waypoints=total_wp,
            waypoints_completed=completed,
            progress_percentage=pct,
            active=(mission.status == MissionStatus.ACTIVE),
        )

    async def update_pose_and_evaluate_progress(self, current_pos: Position3D) -> None:
        """Evaluate if drone reached active waypoint or final destination."""
        if not self._active_mission_id:
            return

        mission = self.repo.get_by_id(self._active_mission_id)
        if not mission or mission.status != MissionStatus.ACTIVE:
            return

        total_wp = len(mission.waypoints)
        threshold = settings.WAYPOINT_REACHED_THRESHOLD

        # If waypoints remain
        if self._active_wp_index < total_wp:
            wp = mission.waypoints[self._active_wp_index]
            dist_to_wp = math.sqrt(
                (current_pos.x - wp.x) ** 2 + (current_pos.y - wp.y) ** 2 + (current_pos.z - wp.z) ** 2
            )
            if dist_to_wp <= threshold:
                # Mark current waypoint REACHED
                self.repo.update_waypoint_status(mission.mission_id, self._active_wp_index, WaypointStatus.REACHED)
                logger.info("Waypoint %d reached (dist=%.2fm)", self._active_wp_index + 1, dist_to_wp)
                
                # Advance to next waypoint
                self._active_wp_index += 1
                if self._active_wp_index < total_wp:
                    self.repo.update_waypoint_status(mission.mission_id, self._active_wp_index, WaypointStatus.CURRENT)
                
                # Broadcast progress update
                progress = self.get_current_progress()
                if progress:
                    await connection_manager.broadcast_json({
                        "event": "mission_progress",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": progress.model_dump(),
                    })
        else:
            # All intermediate waypoints completed, evaluate distance to destination
            dist_to_dest = math.sqrt(
                (current_pos.x - mission.destination.x) ** 2
                + (current_pos.y - mission.destination.y) ** 2
                + (current_pos.z - mission.destination.z) ** 2
            )
            if dist_to_dest <= threshold:
                logger.info("Destination reached! Completing mission %s", mission.mission_id)
                self.repo.update_status(mission.mission_id, MissionStatus.COMPLETED)
                completed_mission = self.get_mission(mission.mission_id)
                self._active_mission_id = None
                await connection_manager.broadcast_json({
                    "event": "mission_status",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "mission_id": mission.mission_id,
                        "status": MissionStatus.COMPLETED.value,
                        "action": "mission_completed",
                        "mission": completed_mission.model_dump() if completed_mission else None,
                    },
                })


mission_service = MissionService()
