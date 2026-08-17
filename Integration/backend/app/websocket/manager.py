"""WebSocket Connection Manager."""

import logging
from typing import Any
from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger("sih_navis.websocket")


class ConnectionManager:
    """Manages active WebSocket client connections and message broadcasting."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    @property
    def active_count(self) -> int:
        """Return the number of currently active connections."""
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept connection and register client."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket client connected. Active clients: %d",
            self.active_count,
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister client connection upon disconnect."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                "WebSocket client disconnected. Active clients: %d",
                self.active_count,
            )

    async def send_personal_message(self, message: str, websocket: WebSocket) -> bool:
        """Send a raw text message to a specific client.

        Returns True if successful, False if failed.
        """
        try:
            await websocket.send_text(message)
            return True
        except Exception as exc:
            logger.warning("WebSocket send personal message failed: %s", exc)
            self.disconnect(websocket)
            return False

    async def send_personal_json(self, data: Any, websocket: WebSocket) -> bool:
        """Send JSON / Pydantic model to a specific client."""
        try:
            if isinstance(data, BaseModel):
                text = data.model_dump_json()
            elif isinstance(data, dict):
                import json
                text = json.dumps(data)
            else:
                text = str(data)
            await websocket.send_text(text)
            return True
        except Exception as exc:
            logger.warning("WebSocket send personal JSON failed: %s", exc)
            self.disconnect(websocket)
            return False

    async def broadcast(self, message: str) -> None:
        """Broadcast a text message to all active clients safely.

        A failure on one client will not prevent other clients from receiving the message.
        """
        disconnected_clients: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as exc:
                logger.warning("WebSocket broadcast send failure for a client: %s", exc)
                disconnected_clients.append(connection)

        for conn in disconnected_clients:
            self.disconnect(conn)

    async def broadcast_json(self, data: Any) -> None:
        """Broadcast JSON / Pydantic model to all active clients."""
        if isinstance(data, BaseModel):
            message = data.model_dump_json()
        elif isinstance(data, dict):
            import json
            message = json.dumps(data)
        else:
            message = str(data)

        await self.broadcast(message)


# Global singleton connection manager
connection_manager = ConnectionManager()
