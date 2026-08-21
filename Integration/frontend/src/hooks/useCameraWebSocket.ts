"use client";

import { useEffect, useRef, useState } from "react";

export function useCameraWebSocket(wsUrl: string = "ws://localhost:8000/ws/camera?role=viewer") {
  const [isConnected, setIsConnected] = useState(false);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [fps, setFps] = useState<number>(0);
  const [frameCount, setFrameCount] = useState<number>(0);

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

        ws.onmessage = (event) => {
          if (unmounted) return;
          if (event.data instanceof Blob) {
            const now = performance.now();
            if (lastTimeRef.current > 0) {
              const dt = (now - lastTimeRef.current) / 1000;
              if (dt > 0) {
                setFps((prev) => Math.round(0.85 * prev + 0.15 * (1.0 / dt)));
              }
            }
            lastTimeRef.current = now;
            frameCountRef.current += 1;
            setFrameCount(frameCountRef.current);

            // Revoke previous blob URL to prevent memory leaks
            if (prevUrlRef.current) {
              URL.revokeObjectURL(prevUrlRef.current);
            }

            const url = URL.createObjectURL(event.data);
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
  };
}
