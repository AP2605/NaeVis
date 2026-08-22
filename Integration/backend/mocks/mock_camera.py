"""Mock Camera Binary Stream Producer.

Generates synthetic RGB drone simulation camera frames (with HUD overlay, artificial horizon,
frame indices, and timestamps), encodes them to JPEG in memory (640x480 @ 15 FPS, quality ~70),
packs them into standardized 20-byte binary header packets [NAVC, frame_id, timestamp, payload_size, JPEG bytes],
and streams binary frames to P4 integration backend over WebSocket (/ws/camera?role=producer).
"""

import argparse
import asyncio
import io
import math
import time
from PIL import Image, ImageDraw, ImageFont
import websockets

from app.schemas.camera_packet import encode_camera_packet


class MockCameraProducer:
    """Generates synthetic JPEG camera frames and streams them as binary packets."""

    def __init__(
        self,
        ws_url: str = "ws://localhost:8000/ws/camera?role=producer",
        fps: float = 15.0,
        width: int = 640,
        height: int = 480,
        quality: int = 70,
        total_frames: int = 0,
    ):
        self.ws_url = ws_url
        self.fps = fps
        self.interval = 1.0 / max(fps, 0.1)
        self.width = width
        self.height = height
        self.quality = quality
        self.total_frames = total_frames
        self.frame_id = 0
        self.start_time = time.monotonic()

    def generate_raw_jpeg_bytes(self) -> bytes:
        """Generate a synthetic camera view image and encode as JPEG bytes in memory."""
        self.frame_id += 1
        elapsed = time.monotonic() - self.start_time

        # Create image with simulated terrain / sky gradient background
        img = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(img)

        # Dynamic artificial horizon / ground and sky colors
        pitch_offset = int(math.cos(elapsed * 0.4) * 25.0)
        horizon_y = (self.height // 2) + pitch_offset

        # Sky background (upper half)
        draw.rectangle([0, 0, self.width, max(0, horizon_y)], fill=(35, 75, 120))
        # Ground background (lower half)
        draw.rectangle([0, max(0, horizon_y), self.width, self.height], fill=(45, 60, 40))

        # Grid lines on ground to simulate optical flow texture
        grid_spacing = 40
        for y in range(max(0, horizon_y), self.height, grid_spacing):
            draw.line([(0, y), (self.width, y)], fill=(60, 80, 50), width=1)
        for x in range(0, self.width, grid_spacing):
            draw.line([(x, max(0, horizon_y)), (x, self.height)], fill=(60, 80, 50), width=1)

        # Draw Crosshair / Drone HUD Reticle
        cx, cy = self.width // 2, self.height // 2
        reticle_size = 28
        hud_color = (0, 255, 128)
        draw.line([(cx - reticle_size, cy), (cx - 10, cy)], fill=hud_color, width=2)
        draw.line([(cx + 10, cy), (cx + reticle_size, cy)], fill=hud_color, width=2)
        draw.line([(cx, cy - reticle_size), (cx, cy - 10)], fill=hud_color, width=2)
        draw.line([(cx, cy + 10), (cx, cy + reticle_size)], fill=hud_color, width=2)
        draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=hud_color, width=1)

        # Pitch ladder ticks
        for p in [-40, 40]:
            py = cy + p + pitch_offset
            if 0 < py < self.height:
                draw.line([(cx - 25, py), (cx + 25, py)], fill=hud_color, width=1)

        # HUD Text telemetry overlay
        font = None
        try:
            font = ImageFont.load_default()
        except Exception:
            pass

        hud_text_top = f"SIH-NAVIS OPTICAL CAM | FRAME: {self.frame_id:05d} | T: {elapsed:.2f}s"
        hud_text_bot = f"FPS: {self.fps:.1f} | RES: {self.width}x{self.height} | Q: {self.quality} | BINARY NAVC"
        draw.text((12, 12), hud_text_top, fill=(255, 255, 255), font=font)
        draw.text((12, self.height - 24), hud_text_bot, fill=hud_color, font=font)

        # Encode to JPEG in-memory buffer (zero disk I/O)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=self.quality)
        return buffer.getvalue()

    def generate_frame_bytes(self) -> bytes:
        """Alias for generate_raw_jpeg_bytes for backward compatibility."""
        return self.generate_raw_jpeg_bytes()

    def generate_packet_bytes(self) -> bytes:
        """Generate structured binary packet [20-byte NAVC header + JPEG payload]."""
        raw_jpeg = self.generate_raw_jpeg_bytes()
        timestamp = time.time()
        return encode_camera_packet(self.frame_id, timestamp, raw_jpeg)

    async def run(self):
        """Connect to camera WebSocket and stream binary packets using monotonic timing."""
        print(f"[Mock Camera] Connecting to {self.ws_url} @ {self.fps} FPS ({self.width}x{self.height}, Q={self.quality})...")
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    print(f"[Mock Camera] Connected! Streaming binary NAVC packets...")
                    count = 0
                    next_frame_time = time.monotonic()
                    while self.total_frames == 0 or count < self.total_frames:
                        packet_bytes = self.generate_packet_bytes()
                        await ws.send(packet_bytes)
                        count += 1

                        if self.frame_id % 30 == 0:
                            print(f"[Mock Camera] Sent frame {self.frame_id} ({len(packet_bytes)} bytes)")

                        next_frame_time += self.interval
                        sleep_time = max(0.0, next_frame_time - time.monotonic())
                        await asyncio.sleep(sleep_time)
                    break
            except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as exc:
                print(f"[Mock Camera] Connection closed/refused ({exc}). Reconnecting in 2s...")
                await asyncio.sleep(2.0)
            except Exception as exc:
                print(f"[Mock Camera] Streaming error: {exc}")
                await asyncio.sleep(2.0)


def main():
    parser = argparse.ArgumentParser(description="Mock Camera Binary Frame Producer")
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws/camera?role=producer",
        help="Camera WebSocket URL",
    )
    parser.add_argument("--fps", type=float, default=15.0, help="Camera frame rate in FPS")
    parser.add_argument("--width", type=int, default=640, help="Image frame width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Image frame height (default: 480)")
    parser.add_argument("--quality", type=int, default=70, help="JPEG quality 1-100 (default: 70)")
    parser.add_argument("--frames", type=int, default=0, help="Total frames to send (0 for continuous)")
    args = parser.parse_args()

    producer = MockCameraProducer(
        ws_url=args.url,
        fps=args.fps,
        width=args.width,
        height=args.height,
        quality=args.quality,
        total_frames=args.frames,
    )
    asyncio.run(producer.run())


if __name__ == "__main__":
    main()
