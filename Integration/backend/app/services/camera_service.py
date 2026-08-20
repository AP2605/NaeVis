"""Camera streaming and frame distribution service."""

import logging
import time
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger("sih_navis.camera")


class CameraService:
    """Manages real-time binary camera streaming and distribution to WebSocket clients."""

    def __init__(self):
        self._viewers: list[WebSocket] = []
        self._producers: list[WebSocket] = []
        self._latest_frame_bytes: bytes | None = None
        self._latest_frame_time: float = 0.0
        self._frame_count: int = 0
        self._fps: float = 0.0

    @property
    def viewer_count(self) -> int:
        """Number of active dashboard camera viewers."""
        return len(self._viewers)

    @property
    def producer_count(self) -> int:
        """Number of active simulation camera feed producers."""
        return len(self._producers)

    async def register_viewer(self, websocket: WebSocket) -> None:
        """Register a frontend client wanting to receive binary video frames."""
        await websocket.accept()
        self._viewers.append(websocket)
        logger.info("Camera viewer connected. Total viewers: %d", self.viewer_count)
        # Send latest frame immediately if available
        if self._latest_frame_bytes is not None:
            try:
                await websocket.send_bytes(self._latest_frame_bytes)
            except Exception as exc:
                logger.debug("Failed sending initial frame to viewer: %s", exc)

    def unregister_viewer(self, websocket: WebSocket) -> None:
        """Remove disconnected camera viewer."""
        if websocket in self._viewers:
            self._viewers.remove(websocket)
            logger.info("Camera viewer disconnected. Remaining viewers: %d", self.viewer_count)

    async def register_producer(self, websocket: WebSocket) -> None:
        """Register a simulation / mock camera producer pushing binary frames."""
        await websocket.accept()
        self._producers.append(websocket)
        logger.info("Camera producer connected. Total producers: %d", self.producer_count)

    def unregister_producer(self, websocket: WebSocket) -> None:
        """Remove disconnected camera producer."""
        if websocket in self._producers:
            self._producers.remove(websocket)
            logger.info("Camera producer disconnected.")

    async def ingest_and_broadcast_frame(self, frame_bytes: bytes) -> None:
        """Ingest raw JPEG/PNG frame and forward directly to all active viewers."""
        now = time.time()
        if self._latest_frame_time > 0:
            dt = now - self._latest_frame_time
            if dt > 0:
                self._fps = 0.9 * self._fps + 0.1 * (1.0 / dt)
        self._latest_frame_time = now
        self._frame_count += 1
        self._latest_frame_bytes = frame_bytes

        if not self._viewers:
            return

        disconnected: list[WebSocket] = []
        for viewer in list(self._viewers):
            try:
                await viewer.send_bytes(frame_bytes)
            except Exception as exc:
                logger.debug("Camera frame broadcast send failure: %s", exc)
                disconnected.append(viewer)

        for conn in disconnected:
            self.unregister_viewer(conn)

    def get_latest_frame(self) -> bytes | None:
        """Return the most recently received raw image bytes."""
        return self._latest_frame_bytes

    def get_stats(self) -> dict[str, Any]:
        """Return camera streaming metrics."""
        return {
            "fps": round(self._fps, 1),
            "total_frames": self._frame_count,
            "viewers": self.viewer_count,
            "producers": self.producer_count,
            "has_frame": self._latest_frame_bytes is not None,
            "last_frame_age_sec": round(time.time() - self._latest_frame_time, 2)
            if self._latest_frame_time > 0
            else None,
        }


# Global singleton instance
camera_service = CameraService()
