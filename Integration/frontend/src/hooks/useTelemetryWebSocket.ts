"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  IntegratedState,
  NavigationStatePacket,
  P1VisionResult,
  SimulationGroundTruthPacket,
  Telemetry,
  WebSocketEvent,
} from "../types/telemetry";

export interface LogEntry {
  id: string;
  time: string;
  type: "info" | "warning" | "error" | "event";
  message: string;
}

export function useTelemetryWebSocket(wsUrl: string = "ws://localhost:8000/ws/telemetry") {
  const [isConnected, setIsConnected] = useState(false);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [integratedState, setIntegratedState] = useState<IntegratedState | null>(null);
  const [groundTruth, setGroundTruth] = useState<SimulationGroundTruthPacket | null>(null);
  const [navigation, setNavigation] = useState<NavigationStatePacket | null>(null);
  const [perception, setPerception] = useState<P1VisionResult | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const addLog = useCallback((message: string, type: LogEntry["type"] = "info") => {
    const entry: LogEntry = {
      id: Math.random().toString(36).substring(2, 9),
      time: new Date().toLocaleTimeString(),
      type,
      message,
    };
    setLogs((prev) => [entry, ...prev.slice(0, 49)]);
  }, []);

  useEffect(() => {
    let unmounted = false;

    function connect() {
      if (unmounted) return;
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (unmounted) return;
          setIsConnected(true);
          addLog(`Telemetry stream connected (${wsUrl.replace(/^ws:\/\/[^/]+/, "")})`, "info");
        };

        ws.onmessage = (event) => {
          if (unmounted) return;
          try {
            const data: WebSocketEvent = JSON.parse(event.data);
            if (data.event === "telemetry") {
              setTelemetry(data.data);
            } else if (data.event === "integrated_state") {
              const state = data.data as IntegratedState;
              setIntegratedState(state);
              if (state.ground_truth) setGroundTruth(state.ground_truth);
              if (state.navigation) setNavigation(state.navigation);
              if (state.perception) setPerception(state.perception);
            } else if (data.event === "ground_truth") {
              setGroundTruth(data.data);
              addLog(`Ground truth frame #${data.data.frame_id ?? ""} received`, "event");
            } else if (data.event === "navigation") {
              setNavigation(data.data);
              const confPct = typeof data.data.confidence === "number" ? `${(data.data.confidence * 100).toFixed(0)}%` : "";
              addLog(`Navigation estimate frame #${data.data.frame_id} (${confPct ? `conf: ${confPct}` : "active"})`, "event");
            } else if (data.event === "perception") {
              setPerception(data.data);
              const terrain = data.data.terrain?.terrain_type ?? "analysis";
              addLog(`Scene analysis frame #${data.data.frame_id} (${terrain})`, "event");
            }
          } catch (err) {
            // Non-JSON message or pong
          }
        };

        ws.onclose = () => {
          if (unmounted) return;
          setIsConnected(false);
          addLog("Telemetry stream disconnected. Reconnecting in 2s...", "warning");
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
    };
  }, [wsUrl, addLog]);

  return {
    isConnected,
    telemetry,
    integratedState,
    groundTruth,
    navigation,
    perception,
    logs,
  };
}
