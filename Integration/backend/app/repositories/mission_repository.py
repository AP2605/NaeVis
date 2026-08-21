"""Mission repository layer for SQLite persistence."""

from datetime import datetime, timezone
import json
import logging
from typing import Any
import uuid

from app.database.db import get_connection
from app.schemas.common import Position3D
from app.schemas.mission import (
    MissionCreate,
    MissionResponse,
    MissionStatus,
    MissionUpdate,
    WaypointCreate,
    WaypointResponse,
    WaypointStatus,
)

logger = logging.getLogger("sih_navis.repository.mission")


class MissionRepository:
    """Repository handling SQL operations for missions and waypoints."""

    def create(self, mission_in: MissionCreate) -> MissionResponse:
        """Create and persist a new mission with associated waypoints."""
        conn = get_connection()
        try:
            mission_id = str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()

            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO missions (
                    mission_id, mission_name, source_x, source_y, source_z,
                    destination_x, destination_y, destination_z, coordinate_frame,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    mission_in.mission_name,
                    mission_in.source.x,
                    mission_in.source.y,
                    mission_in.source.z,
                    mission_in.destination.x,
                    mission_in.destination.y,
                    mission_in.destination.z,
                    mission_in.coordinate_frame,
                    MissionStatus.DRAFT.value,
                    now_iso,
                    now_iso,
                ),
            )

            waypoints_resp: list[WaypointResponse] = []
            for idx, wp in enumerate(mission_in.waypoints):
                cursor.execute(
                    """
                    INSERT INTO waypoints (mission_id, waypoint_index, x, y, z, status, name)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mission_id,
                        idx,
                        wp.x,
                        wp.y,
                        wp.z,
                        WaypointStatus.PENDING.value,
                        wp.name,
                    ),
                )
                waypoints_resp.append(
                    WaypointResponse(
                        id=cursor.lastrowid,
                        waypoint_index=idx,
                        x=wp.x,
                        y=wp.y,
                        z=wp.z,
                        status=WaypointStatus.PENDING,
                        name=wp.name,
                    )
                )

            conn.commit()
            return MissionResponse(
                mission_id=mission_id,
                mission_name=mission_in.mission_name,
                source=mission_in.source,
                destination=mission_in.destination,
                waypoints=waypoints_resp,
                coordinate_frame=mission_in.coordinate_frame,
                status=MissionStatus.DRAFT,
                created_at=now_iso,
                updated_at=now_iso,
            )
        except Exception as exc:
            conn.rollback()
            logger.error("Failed to create mission: %s", exc)
            raise
        finally:
            conn.close()

    def get_by_id(self, mission_id: str) -> MissionResponse | None:
        """Fetch mission by UUID including ordered waypoints."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,))
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                "SELECT * FROM waypoints WHERE mission_id = ? ORDER BY waypoint_index ASC",
                (mission_id,),
            )
            wp_rows = cursor.fetchall()
            waypoints = [
                WaypointResponse(
                    id=wp["id"],
                    waypoint_index=wp["waypoint_index"],
                    x=wp["x"],
                    y=wp["y"],
                    z=wp["z"],
                    status=WaypointStatus(wp["status"]),
                    name=wp["name"],
                )
                for wp in wp_rows
            ]

            return MissionResponse(
                mission_id=row["mission_id"],
                mission_name=row["mission_name"],
                source=Position3D(x=row["source_x"], y=row["source_y"], z=row["source_z"]),
                destination=Position3D(
                    x=row["destination_x"], y=row["destination_y"], z=row["destination_z"]
                ),
                waypoints=waypoints,
                coordinate_frame=row["coordinate_frame"],
                status=MissionStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        finally:
            conn.close()

    def list_all(self, limit: int = 50, offset: int = 0) -> list[MissionResponse]:
        """List all stored missions in reverse chronological order."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mission_id FROM missions ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            missions: list[MissionResponse] = []
            for r in rows:
                m = self.get_by_id(r["mission_id"])
                if m:
                    missions.append(m)
            return missions
        finally:
            conn.close()

    def update(self, mission_id: str, update_in: MissionUpdate) -> MissionResponse | None:
        """Update mission fields and optionally replace waypoints."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,))
            row = cursor.fetchone()
            if not row:
                return None

            now_iso = datetime.now(timezone.utc).isoformat()
            fields: list[str] = ["updated_at = ?"]
            params: list[Any] = [now_iso]

            if update_in.mission_name is not None:
                fields.append("mission_name = ?")
                params.append(update_in.mission_name)
            if update_in.source is not None:
                fields.extend(["source_x = ?", "source_y = ?", "source_z = ?"])
                params.extend([update_in.source.x, update_in.source.y, update_in.source.z])
            if update_in.destination is not None:
                fields.extend(["destination_x = ?", "destination_y = ?", "destination_z = ?"])
                params.extend([update_in.destination.x, update_in.destination.y, update_in.destination.z])
            if update_in.coordinate_frame is not None:
                fields.append("coordinate_frame = ?")
                params.append(update_in.coordinate_frame)
            if update_in.status is not None:
                fields.append("status = ?")
                params.append(update_in.status.value)

            params.append(mission_id)
            query = f"UPDATE missions SET {', '.join(fields)} WHERE mission_id = ?"
            cursor.execute(query, params)

            if update_in.waypoints is not None:
                cursor.execute("DELETE FROM waypoints WHERE mission_id = ?", (mission_id,))
                for idx, wp in enumerate(update_in.waypoints):
                    cursor.execute(
                        """
                        INSERT INTO waypoints (mission_id, waypoint_index, x, y, z, status, name)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (mission_id, idx, wp.x, wp.y, wp.z, WaypointStatus.PENDING.value, wp.name),
                    )

            conn.commit()
            return self.get_by_id(mission_id)
        except Exception as exc:
            conn.rollback()
            logger.error("Failed to update mission %s: %s", mission_id, exc)
            raise
        finally:
            conn.close()

    def update_status(self, mission_id: str, status: MissionStatus) -> MissionResponse | None:
        """Update only the status of a mission."""
        return self.update(mission_id, MissionUpdate(status=status))

    def update_waypoint_status(self, mission_id: str, waypoint_index: int, status: WaypointStatus) -> bool:
        """Update status of a specific waypoint within a mission."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE waypoints SET status = ? WHERE mission_id = ? AND waypoint_index = ?",
                (status.value, mission_id, waypoint_index),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete(self, mission_id: str) -> bool:
        """Delete a mission and its waypoints."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM waypoints WHERE mission_id = ?", (mission_id,))
            cursor.execute("DELETE FROM missions WHERE mission_id = ?", (mission_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


mission_repository = MissionRepository()
