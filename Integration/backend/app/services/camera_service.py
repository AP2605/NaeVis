"""Camera streaming, multi-consumer distribution, and SLAM bridge service."""

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Set
from fastapi import WebSocket

from app.schemas.camera_packet import (
    decode_camera_packet,
    encode_camera_packet,
)

logger = logging.getLogger("sih_navis.camera")


class CameraService:
    """Manages real-time binary camera streaming and low-latency frame fan-out.

    Distributes single captured camera frames across:
    - Existing Camera Viewers (/ws/camera)
    - SLAM Algorithm Consumers (/ws/slam)
    - Frontend Live Video Stream (/ws/video)
    - In-process SLAM Hooks / Callbacks
    """

    def __init__(self):
        self._camera_viewers: Set[WebSocket] = set()
        self._slam_consumers: Set[WebSocket] = set()
        self._video_consumers: Set[WebSocket] = set()
        self._producers: Set[WebSocket] = set()

        # In-process SLAM subscription callbacks: fn(frame_id, timestamp, jpeg_bytes)
        self._slam_callbacks: list[Callable[[int, float, bytes], Coroutine[Any, Any, None] | None]] = []

        # Latest frame state cache
        self._latest_packet_bytes: bytes | None = None
        self._latest_raw_jpeg: bytes | None = None
        self._latest_frame_id: int = 0
        self._latest_timestamp: float = 0.0
        self._latest_frame_time: float = 0.0
        self._frame_count: int = 0
        self._fps: float = 0.0

    @property
    def viewer_count(self) -> int:
        """Total number of active camera viewers (/ws/camera)."""
        return len(self._camera_viewers)

    @property
    def slam_consumer_count(self) -> int:
        """Number of active SLAM consumers (/ws/slam)."""
        return len(self._slam_consumers)

    @property
    def video_consumer_count(self) -> int:
        """Number of active video display consumers (/ws/video)."""
        return len(self._video_consumers)

    @property
    def producer_count(self) -> int:
        """Number of active camera feed producers."""
        return len(self._producers)

    @property
    def total_consumers(self) -> int:
        """Total distinct downstream clients across all channels."""
        return len(self._camera_viewers | self._slam_consumers | self._video_consumers)

    # -------------------------------------------------------------------------
    # Registration & Lifecycle Management
    # -------------------------------------------------------------------------

    async def register_viewer(self, websocket: WebSocket) -> None:
        """Register a legacy /ws/camera viewer client."""
        if getattr(websocket.client_state, "name", "") != "CONNECTED":
            await websocket.accept()
        self._camera_viewers.add(websocket)
        logger.info("[CameraService] /ws/camera viewer connected. Total: %d", self.viewer_count)
        if self._latest_raw_jpeg is not None:
            try:
                await websocket.send_bytes(self._latest_raw_jpeg)
            except Exception as exc:
                logger.debug("Failed sending initial frame to /ws/camera viewer: %s", exc)

    def unregister_viewer(self, websocket: WebSocket) -> None:
        """Remove disconnected /ws/camera viewer."""
        self._camera_viewers.discard(websocket)
        logger.info("[CameraService] /ws/camera viewer disconnected. Remaining: %d", self.viewer_count)

    async def register_slam_consumer(self, websocket: WebSocket) -> None:
        """Register a /ws/slam client wanting structured binary packets [header + JPEG]."""
        if getattr(websocket.client_state, "name", "") != "CONNECTED":
            await websocket.accept()
        self._slam_consumers.add(websocket)
        logger.info("[CameraService] /ws/slam consumer connected. Total: %d", self.slam_consumer_count)
        if self._latest_packet_bytes is not None:
            try:
                await websocket.send_bytes(self._latest_packet_bytes)
            except Exception as exc:
                logger.debug("Failed sending initial packet to /ws/slam: %s", exc)

    def unregister_slam_consumer(self, websocket: WebSocket) -> None:
        """Remove disconnected /ws/slam consumer."""
        self._slam_consumers.discard(websocket)
        logger.info("[CameraService] /ws/slam consumer disconnected. Remaining: %d", self.slam_consumer_count)

    async def register_video_consumer(self, websocket: WebSocket) -> None:
        """Register a /ws/video frontend live video client."""
        if getattr(websocket.client_state, "name", "") != "CONNECTED":
            await websocket.accept()
        self._video_consumers.add(websocket)
        logger.info("[CameraService] /ws/video consumer connected. Total: %d", self.video_consumer_count)
        if self._latest_packet_bytes is not None:
            try:
                await websocket.send_bytes(self._latest_packet_bytes)
            except Exception as exc:
                logger.debug("Failed sending initial packet to /ws/video: %s", exc)

    def unregister_video_consumer(self, websocket: WebSocket) -> None:
        """Remove disconnected /ws/video consumer."""
        self._video_consumers.discard(websocket)
        logger.info("[CameraService] /ws/video consumer disconnected. Remaining: %d", self.video_consumer_count)

    async def register_producer(self, websocket: WebSocket) -> None:
        """Register an upstream frame source (Blender simulation / Mock camera)."""
        if getattr(websocket.client_state, "name", "") != "CONNECTED":
            await websocket.accept()
        self._producers.add(websocket)
        logger.info("[CameraService] Camera producer connected. Total producers: %d", self.producer_count)

    def unregister_producer(self, websocket: WebSocket) -> None:
        """Remove disconnected camera producer."""
        self._producers.discard(websocket)
        logger.info("[CameraService] Camera producer disconnected.")

    def register_slam_callback(
        self, callback: Callable[[int, float, bytes], Coroutine[Any, Any, None] | None]
    ) -> None:
        """Register an in-process SLAM processing hook."""
        if callback not in self._slam_callbacks:
            self._slam_callbacks.append(callback)
            logger.info("[CameraService] Registered in-process SLAM callback.")

    def unregister_slam_callback(
        self, callback: Callable[[int, float, bytes], Coroutine[Any, Any, None] | None]
    ) -> None:
        """Unregister an in-process SLAM hook."""
        if callback in self._slam_callbacks:
            self._slam_callbacks.remove(callback)

    # -------------------------------------------------------------------------
    # Ingestion & Multi-Channel Fan-Out
    # -------------------------------------------------------------------------

    async def ingest_and_broadcast_frame(self, incoming_bytes: bytes) -> dict[str, Any]:
        """Ingest raw binary packet from Blender/producer and distribute to all consumers.

        Preserves frame_id and timestamp across all channels:
        - Decodes header metadata from incoming packet.
        - Packs standard 20-byte NAVC packet for SLAM and Video consumers.
        - Distributes raw JPEG to legacy /ws/camera viewers.
        - Non-blocking: drops stale frame for any slow client without blocking the stream.

        Args:
            incoming_bytes: Binary message from producer.

        Returns:
            dict containing parsed frame metadata (frame_id, timestamp, payload_size).
        """
        now = time.time()
        try:
            parsed_frame_id, parsed_ts, jpeg_bytes = decode_camera_packet(incoming_bytes)
        except ValueError as err:
            logger.warning("[CameraService] Rejected invalid camera frame: %s", err)
            return {"error": str(err)}

        # Update frame indexing
        self._frame_count += 1
        frame_id = parsed_frame_id if parsed_frame_id > 0 else self._frame_count
        timestamp = parsed_ts if parsed_ts > 0 else now

        # Update FPS calculation (exponential moving average)
        if self._latest_frame_time > 0:
            dt = now - self._latest_frame_time
            if dt > 0:
                self._fps = 0.85 * self._fps + 0.15 * (1.0 / dt)
        self._latest_frame_time = now

        # Prepare standardized binary packet [20-byte header + JPEG bytes]
        packet_bytes = encode_camera_packet(frame_id, timestamp, jpeg_bytes)

        # Cache latest state
        self._latest_frame_id = frame_id
        self._latest_timestamp = timestamp
        self._latest_raw_jpeg = jpeg_bytes
        self._latest_packet_bytes = packet_bytes

        # Asynchronously dispatch to all connected channels with error resilience
        asyncio.create_task(self._fanout_frame(packet_bytes, jpeg_bytes, frame_id, timestamp))

        return {
            "frame_id": frame_id,
            "timestamp": timestamp,
            "payload_size": len(jpeg_bytes),
        }

    async def _fanout_frame(
        self, packet_bytes: bytes, raw_jpeg: bytes, frame_id: int, timestamp: float
    ) -> None:
        """Internal non-blocking multi-consumer broadcaster."""
        # 1. Dispatch to /ws/slam consumers (receives structured binary packet)
        if self._slam_consumers:
            disconnected_slam = []
            for ws in list(self._slam_consumers):
                try:
                    await ws.send_bytes(packet_bytes)
                except Exception as exc:
                    logger.debug("[CameraService] SLAM send dropped/failed: %s", exc)
                    disconnected_slam.append(ws)
            for ws in disconnected_slam:
                self.unregister_slam_consumer(ws)

        # 2. Dispatch to /ws/video consumers (receives structured binary packet)
        if self._video_consumers:
            disconnected_video = []
            for ws in list(self._video_consumers):
                try:
                    await ws.send_bytes(packet_bytes)
                except Exception as exc:
                    logger.debug("[CameraService] Video send dropped/failed: %s", exc)
                    disconnected_video.append(ws)
            for ws in disconnected_video:
                self.unregister_video_consumer(ws)

        # 3. Dispatch to legacy /ws/camera viewers (receives raw JPEG bytes)
        if self._camera_viewers:
            disconnected_camera = []
            for ws in list(self._camera_viewers):
                try:
                    await ws.send_bytes(raw_jpeg)
                except Exception as exc:
                    logger.debug("[CameraService] Camera viewer send failed: %s", exc)
                    disconnected_camera.append(ws)
            for ws in disconnected_camera:
                self.unregister_viewer(ws)

        # 4. Trigger registered in-process SLAM hooks
        for cb in self._slam_callbacks:
            try:
                res = cb(frame_id, timestamp, raw_jpeg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as cb_exc:
                logger.warning("[CameraService] SLAM callback error: %s", cb_exc)

    def reset(self) -> None:
        """Reset cached frame state and counters."""
        self._latest_packet_bytes = None
        self._latest_raw_jpeg = None
        self._latest_frame_id = 0
        self._latest_timestamp = 0.0
        self._latest_frame_time = 0.0
        self._frame_count = 0
        self._fps = 0.0

    def get_latest_frame(self) -> bytes | None:
        """Return the most recently received raw image bytes."""
        return self._latest_raw_jpeg

    def get_latest_packet(self) -> bytes | None:
        """Return the most recently received structured binary packet."""
        return self._latest_packet_bytes

    def get_stats(self) -> dict[str, Any]:
        """Return camera streaming metrics and consumer counts."""
        return {
            "fps": round(self._fps, 1),
            "total_frames": self._frame_count,
            "latest_frame_id": self._latest_frame_id,
            "latest_timestamp": round(self._latest_timestamp, 3),
            "viewers": self.viewer_count,
            "slam_consumers": self.slam_consumer_count,
            "video_consumers": self.video_consumer_count,
            "producers": self.producer_count,
            "has_frame": self._latest_raw_jpeg is not None,
            "last_frame_age_sec": round(time.time() - self._latest_frame_time, 2)
            if self._latest_frame_time > 0
            else None,
        }


# Global singleton instance
camera_service = CameraService()
