"""WebSocket event and message schemas."""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

from app.schemas.telemetry import Telemetry

T = TypeVar("T")


class WebSocketEvent(BaseModel, Generic[T]):
    """Generic WebSocket event envelope for all real-time events."""

    event: str = Field(..., description="Event type identifier (e.g., 'telemetry')")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the event envelope",
    )
    data: T = Field(..., description="Payload data corresponding to the event type")

    model_config = {
        "json_schema_extra": {
            "example": {
                "event": "telemetry",
                "timestamp": "2026-08-17T12:00:00Z",
                "data": {
                    "x": 12.4,
                    "y": 7.2,
                    "z": 15.8,
                    "velocity": 4.6,
                    "roll": 0.4,
                    "pitch": -0.8,
                    "yaw": 91.2,
                    "confidence": 0.94,
                    "timestamp": "2026-08-17T12:00:00Z",
                },
            }
        }
    }


class TelemetryEvent(WebSocketEvent[Telemetry]):
    """Specialized WebSocket event envelope for telemetry payloads."""

    event: str = Field(default="telemetry", description="Event type identifier fixed to 'telemetry'")


class WebSocketClientMessage(BaseModel):
    """Schema for incoming client messages."""

    type: str = Field(default="ping", description="Message type (e.g. 'ping')")
    payload: dict[str, Any] = Field(default_factory=dict, description="Optional message payload")
