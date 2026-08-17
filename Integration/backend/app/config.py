"""Configuration settings for SIH-NAVIS Backend."""

import os


class Settings:
    """Backend application settings."""

    APP_NAME: str = "SIH-NAVIS Backend"
    APP_DESCRIPTION: str = (
        "Backend service for the SIH-NAVIS GPS-denied autonomous drone navigation simulation system."
    )
    APP_VERSION: str = "0.1.0"

    # Telemetry streaming interval in seconds (0.1s = 100ms = 10 Hz)
    TELEMETRY_STREAM_INTERVAL: float = float(os.getenv("TELEMETRY_STREAM_INTERVAL", "0.1"))

    # Logging level
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
