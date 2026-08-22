"use client";

import { useEffect, useRef, useState } from "react";

export interface CameraStreamState {
  isConnected: boolean;
  imageSrc: string | null;
  fps: number;
  frameCount: number;
  frameId?: number;
  timestamp?: number;
}

export function useCameraWebSocket(
  wsUrl: string = "ws://localhost:8000/ws/video"
): CameraStreamState {
  const [isConnected, setIsConnected] = useState(false);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [fps, setFps] = useState<number>(0);
  const [frameCount, setFrameCount] = useState<number>(0);
  const [frameId, setFrameId] = useState<number | undefined>(undefined);
  const [timestamp, setTimestamp] = useState<number | undefined>(undefined);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastTimeRef = useRef<number>(0);
  const frameCountRef = useRef<number>(0);
  const prevUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let unmounted = false;

    function connect() {
      if (unmounted) return;
      try {
        const ws = new WebSocket(wsUrl);
        ws.binaryType = "blob";
        wsRef.current = ws;

        ws.onopen = () => {
          if (unmounted) return;
          setIsConnected(true);
        };

        ws.onmessage = async (event) => {
          if (unmounted) return;
          if (event.data instanceof Blob) {
            const blob = event.data;
            const now = performance.now();

            // Calculate live FPS (exponential moving average)
            if (lastTimeRef.current > 0) {
              const dt = (now - lastTimeRef.current) / 1000;
              if (dt > 0) {
                setFps((prev) => Math.round(0.85 * prev + 0.15 * (1.0 / dt)));
              }
            }
            lastTimeRef.current = now;
            frameCountRef.current += 1;
            setFrameCount(frameCountRef.current);

            let jpegBlob: Blob = blob;

            // Inspect binary header for standard 20-byte NAVC packet
            if (blob.size >= 20) {
              try {
                const headerBuffer = await blob.slice(0, 20).arrayBuffer();
                const view = new DataView(headerBuffer);
                const magic0 = view.getUint8(0);
                const magic1 = view.getUint8(1);
                const magic2 = view.getUint8(2);
                const magic3 = view.getUint8(3);

                // Check magic "NAVC" (0x4E, 0x41, 0x56, 0x43)
                if (
                  magic0 === 0x4e &&
                  magic1 === 0x41 &&
                  magic2 === 0x56 &&
                  magic3 === 0x43
                ) {
                  const fId = view.getUint32(4, false); // big-endian
                  const ts = view.getFloat64(8, false);  // big-endian
                  setFrameId(fId);
                  setTimestamp(ts);
                  // Slice pure JPEG payload (bytes 20 onwards)
                  jpegBlob = blob.slice(20);
                }
              } catch {
                // Fallback to direct blob if header parse fails
              }
            }

            // Revoke previous Blob URL immediately to prevent browser memory leaks
            if (prevUrlRef.current) {
              URL.revokeObjectURL(prevUrlRef.current);
            }

            const url = URL.createObjectURL(jpegBlob);
            prevUrlRef.current = url;
            setImageSrc(url);
          }
        };

        ws.onclose = () => {
          if (unmounted) return;
          setIsConnected(false);
          reconnectTimeoutRef.current = setTimeout(connect, 2000);
        };

        ws.onerror = () => {
          if (unmounted) return;
          setIsConnected(false);
        };
      } catch (err) {
        if (!unmounted) {
          reconnectTimeoutRef.current = setTimeout(connect, 2000);
        }
      }
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
      if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current);
    };
  }, [wsUrl]);

  return {
    isConnected,
    imageSrc,
    fps,
    frameCount,
    frameId,
    timestamp,
  };
}
