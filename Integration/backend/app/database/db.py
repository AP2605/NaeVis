"""Database connection and initialization module for SIH-NAVIS.

Provides lightweight SQLite persistence for missions, waypoints, and trajectory samples.
Designed with repository pattern so that switching to PostgreSQL in future is seamless.
"""

import logging
import os
import sqlite3
from app.config import settings

logger = logging.getLogger("sih_navis.database")


def get_db_path() -> str:
    """Return the absolute path to the SQLite database file."""
    db_path = settings.DATABASE_PATH
    if not os.path.isabs(db_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(base_dir, db_path)
    return db_path


_db_initialized = False


def get_connection() -> sqlite3.Connection:
    """Create and return a new SQLite database connection with row factory."""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True
    conn = sqlite3.connect(get_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Initialize database tables if they do not already exist."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cursor = conn.cursor()

        # Missions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS missions (
                mission_id TEXT PRIMARY KEY,
                mission_name TEXT NOT NULL,
                source_x REAL NOT NULL,
                source_y REAL NOT NULL,
                source_z REAL NOT NULL,
                destination_x REAL NOT NULL,
                destination_y REAL NOT NULL,
                destination_z REAL NOT NULL,
                coordinate_frame TEXT NOT NULL DEFAULT 'BLENDER_LOCAL',
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Waypoints table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS waypoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                waypoint_index INTEGER NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                z REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                name TEXT,
                FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE,
                UNIQUE (mission_id, waypoint_index)
            )
            """
        )

        # Trajectory samples table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trajectory_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT,
                frame_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                gt_x REAL,
                gt_y REAL,
                gt_z REAL,
                gt_roll REAL,
                gt_pitch REAL,
                gt_yaw REAL,
                est_x REAL,
                est_y REAL,
                est_z REAL,
                est_roll REAL,
                est_pitch REAL,
                est_yaw REAL,
                error_3d REAL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_waypoints_mission ON waypoints (mission_id, waypoint_index)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trajectory_frame ON trajectory_samples (frame_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trajectory_mission ON trajectory_samples (mission_id)")

        conn.commit()
        logger.info("Database initialized successfully at: %s", db_path)
    except Exception as exc:
        logger.error("Failed to initialize database: %s", exc)
        conn.rollback()
        raise
    finally:
        conn.close()
