"""Configuration settings for SIH-NAVIS Backend."""

import os


class Settings:
    """Backend application settings."""

    APP_NAME: str = "SIH-NAVIS Integration Backend"
    APP_DESCRIPTION: str = (
        "Backend service for the SIH-NAVIS GPS-denied autonomous drone navigation simulation system. "
        "Integrates P1 (Perception), P2 (Simulation Ground Truth + Camera), and P3 (Navigation)."
    )
    APP_VERSION: str = "0.1.0"

    # Server settings
    HOST: str = os.getenv("P4_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("P4_PORT", "8000"))

    # External Module Base URLs
    P1_BASE_URL: str = os.getenv("P1_BASE_URL", "http://localhost:8001")
    P2_BASE_URL: str = os.getenv("P2_BASE_URL", "http://localhost:8002")
    P3_BASE_URL: str = os.getenv("P3_BASE_URL", "http://localhost:8003")

    # Telemetry streaming interval in seconds (0.1s = 100ms = 10 Hz)
    TELEMETRY_STREAM_INTERVAL: float = float(os.getenv("TELEMETRY_STREAM_INTERVAL", "0.1"))

    # Camera settings
    CAMERA_FPS: float = float(os.getenv("CAMERA_FPS", "15.0"))
    CAMERA_WS_PATH: str = "/ws/camera"
    TELEMETRY_WS_PATH: str = "/ws/telemetry"

    # Frame synchronization settings
    FRAME_SYNC_BUFFER_SIZE: int = int(os.getenv("FRAME_SYNC_BUFFER_SIZE", "500"))
    FRAME_SYNC_TOLERANCE_SEC: float = float(os.getenv("FRAME_SYNC_TOLERANCE_SEC", "0.5"))

    # M4 Additions: Trajectory, Mission & Analytics Settings
    MAX_TRAJECTORY_POINTS: int = int(os.getenv("MAX_TRAJECTORY_POINTS", "1000"))
    WAYPOINT_REACHED_THRESHOLD: float = float(os.getenv("WAYPOINT_REACHED_THRESHOLD", "3.0"))
    ANALYTICS_SAMPLE_LIMIT: int = int(os.getenv("ANALYTICS_SAMPLE_LIMIT", "500"))
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "sih_navis.db")

    # M6 Additions: Source Health, Stale Timeout & Adapter Settings
    STALE_TIMEOUT_SEC: float = float(os.getenv("STALE_TIMEOUT_SEC", "3.0"))
    CAMERA_MAX_FRAME_SIZE: int = int(os.getenv("CAMERA_MAX_FRAME_SIZE", str(10 * 1024 * 1024)))
    SOURCE_MODE: str = os.getenv("SOURCE_MODE", "AUTO")  # "AUTO", "MOCK", "REAL"

    # Logging level
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()

