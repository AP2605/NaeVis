"use client";

import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { CameraStream } from "../components/CameraStream";
import { MissionControl } from "../components/MissionControl";

const Navigation3DView = dynamic(
  () => import("../components/Navigation3DView").then((mod) => mod.Navigation3DView),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full min-h-[380px] bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-center text-slate-500 font-mono text-xs">
        Initializing 3D Engine...
      </div>
    ),
  }
);
import { AnalyticsCard } from "../components/AnalyticsCard";
import { PoseComparisonCard } from "../components/PoseComparisonCard";
import { PerceptionCard } from "../components/PerceptionCard";
import { TelemetryCard } from "../components/TelemetryCard";
import { EventLogCard } from "../components/EventLogCard";
import { useTelemetryWebSocket } from "../hooks/useTelemetryWebSocket";
import { useCameraWebSocket } from "../hooks/useCameraWebSocket";
import { Compass, Radio, ShieldCheck, Activity, Layers, Cpu, Video, Navigation as NavIcon, Eye } from "lucide-react";
import { Mission, SourceHealth, TrajectoryData } from "../types/telemetry";

function SourceStatusBadge({
  label,
  icon: Icon,
  health,
  fallbackActive,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  health?: SourceHealth;
  fallbackActive?: boolean;
}) {
  const state = health?.state ?? (fallbackActive ? "MOCK" : "DISCONNECTED");
  const isReal = health?.is_real ?? false;
  const rate = health?.rate_hz ?? 0;

  let badgeClass = "bg-slate-950 text-slate-400 border-slate-800";
  let dotClass = "bg-slate-600";
  let displayState: string = state;

  if (state === "CONNECTED" || (isReal && state === "MOCK")) {
    badgeClass = "bg-emerald-950/70 text-emerald-300 border-emerald-500/40";
    dotClass = "bg-emerald-400 animate-pulse";
    displayState = "REAL / ONLINE";
  } else if (state === "MOCK") {
    badgeClass = "bg-cyan-950/70 text-cyan-300 border-cyan-500/40";
    dotClass = "bg-cyan-400 animate-pulse";
    displayState = "MOCK SIM";
  } else if (state === "STALE") {
    badgeClass = "bg-amber-950/70 text-amber-300 border-amber-500/40";
    dotClass = "bg-amber-400";
    displayState = "STALE (NO DATA)";
  } else if (state === "ERROR") {
    badgeClass = "bg-rose-950/70 text-rose-300 border-rose-500/40";
    dotClass = "bg-rose-500";
    displayState = "ERROR";
  } else {
    badgeClass = "bg-slate-950/90 text-slate-500 border-slate-800/80";
    dotClass = "bg-slate-600";
    displayState = "OFFLINE";
  }

  return (
    <div className={`px-2 py-1 rounded border flex items-center gap-1.5 font-mono text-[10.5px] transition-all shadow-sm ${badgeClass}`}>
      <Icon className="w-3 h-3 stroke-[2] opacity-80" />
      <span className="font-semibold text-slate-200 font-sans tracking-tight">{label}:</span>
      <span className="flex items-center gap-1 font-medium">
        <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
        <span>{displayState}</span>
      </span>
      {rate > 0 && <span className="text-[10px] text-slate-400 font-normal">({rate.toFixed(1)} Hz)</span>}
    </div>
  );
}

export default function DashboardPage() {
  const [host, setHost] = useState("localhost");

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hostname) {
      setHost(window.location.hostname);
    }
  }, []);

  const apiBaseUrl = `http://${host}:8000`;
  const wsTelemetryUrl = `ws://${host}:8000/ws/telemetry`;
  const wsCameraUrl = `ws://${host}:8000/ws/video`;

  const {
    isConnected: isTelemetryConnected,
    telemetry,
    integratedState,
    groundTruth,
    navigation,
    perception,
    analytics,
    missionEvent,
    logs,
  } = useTelemetryWebSocket(wsTelemetryUrl);

  const {
    isConnected: isCameraConnected,
    imageSrc,
    fps: cameraFps,
    frameCount: cameraFrames,
  } = useCameraWebSocket(wsCameraUrl);

  const [activeMission, setActiveMission] = useState<Mission | null>(null);
  const [trajectoryHistory, setTrajectoryHistory] = useState<TrajectoryData | null>(null);

  // Live real-time trajectory trails updated frame-by-frame
  const [liveEstimated, setLiveEstimated] = useState<any[]>([]);
  const [liveGroundTruth, setLiveGroundTruth] = useState<any[]>([]);

  // Initial mount data loading (Active mission, initial trajectory, initial analytics)
  useEffect(() => {
    async function loadInitialState() {
      // 1. Fetch active or latest mission
      try {
        const mRes = await fetch(`${apiBaseUrl}/api/v1/missions/active/current`);
        if (mRes.ok) {
          const m = await mRes.json();
          if (m && m.mission_id) {
            setActiveMission(m);
          }
        }
      } catch (err) {
        // Backend starting
      }

      // 2. Fetch initial trajectory history
      try {
        const tRes = await fetch(`${apiBaseUrl}/api/v1/trajectory?limit=500`);
        if (tRes.ok) {
          const data: TrajectoryData = await tRes.json();
          setTrajectoryHistory(data);
          if (data.estimated) setLiveEstimated(data.estimated);
          if (data.ground_truth) setLiveGroundTruth(data.ground_truth);
        }
      } catch (err) {
        // Backend starting
      }
    }

    loadInitialState();
  }, []);

  // Poll trajectory history from REST API periodically to sync with backend DB
  useEffect(() => {
    let timer: NodeJS.Timeout;
    async function fetchTrajectory() {
      try {
        const res = await fetch(`${apiBaseUrl}/api/v1/trajectory?limit=500`);
        if (res.ok) {
          const data: TrajectoryData = await res.json();
          setTrajectoryHistory(data);
        }
      } catch (err) {
        // Backend offline / starting
      }
    }

    timer = setInterval(fetchTrajectory, 2000);
    return () => clearInterval(timer);
  }, []);

  // Incrementally append live navigation point to trajectory trail on each frame
  useEffect(() => {
    if (navigation?.estimated_pose) {
      const pt = {
        frame_id: navigation.frame_id,
        timestamp: navigation.timestamp,
        x: navigation.estimated_pose.x,
        y: navigation.estimated_pose.y,
        z: navigation.estimated_pose.z,
        roll: navigation.estimated_pose.roll ?? 0,
        pitch: navigation.estimated_pose.pitch ?? 0,
        yaw: navigation.estimated_pose.yaw ?? 0,
      };
      setLiveEstimated((prev) => [...prev.slice(-499), pt]);
    }
  }, [navigation?.frame_id, navigation?.timestamp]);

  // Incrementally append live ground truth point to trajectory trail on each frame
  useEffect(() => {
    if (groundTruth?.position) {
      const pt = {
        frame_id: groundTruth.frame_id ?? 0,
        timestamp: groundTruth.timestamp,
        x: groundTruth.position.x,
        y: groundTruth.position.y,
        z: groundTruth.position.z,
        roll: groundTruth.orientation?.roll ?? 0,
        pitch: groundTruth.orientation?.pitch ?? 0,
        yaw: groundTruth.orientation?.yaw ?? 0,
      };
      setLiveGroundTruth((prev) => [...prev.slice(-499), pt]);
    }
  }, [groundTruth?.frame_id, groundTruth?.timestamp]);

  // Update active mission from WebSocket events
  useEffect(() => {
    if (!missionEvent) return;

    if (missionEvent.mission) {
      setActiveMission(missionEvent.mission);
      return;
    }

    if (missionEvent.mission_id) {
      if (!activeMission || activeMission.mission_id !== missionEvent.mission_id) {
        fetch(`${apiBaseUrl}/api/v1/missions/${missionEvent.mission_id}`)
          .then((r) => (r.ok ? r.json() : null))
          .then((m) => {
            if (m) setActiveMission(m);
          })
          .catch(() => {});
      } else {
        setActiveMission((prev) => {
          if (!prev) return prev;
          const updated = { ...prev };
          if (missionEvent.status) updated.status = missionEvent.status;
          if (missionEvent.progress_percentage !== undefined) {
            updated.progress = missionEvent;
          }
          return updated;
        });
      }
    }
  }, [missionEvent, activeMission?.mission_id]);

  const currentFrame =
    integratedState?.current_frame_id ??
    navigation?.frame_id ??
    groundTruth?.frame_id ??
    perception?.frame_id ??
    0;

  const currentTimestamp =
    integratedState?.latest_timestamp ??
    navigation?.timestamp ??
    groundTruth?.timestamp ??
    0.0;

  return (
    <main className="min-h-screen w-full px-3.5 sm:px-5 lg:px-6 py-3.5 flex flex-col gap-3.5 bg-slate-950 text-slate-100 font-sans">
      {/* Top Operations Header Bar */}
      <header className="bg-slate-900 border border-slate-800 rounded-lg p-3 sm:p-3.5 flex flex-wrap items-center justify-between gap-3 shadow-md">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-slate-950 border border-slate-800 text-cyan-400">
            <Compass className="w-5 h-5 stroke-[2]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold tracking-tight text-white">
                NaeVis
              </h1>
              <span className="bg-cyan-950 border border-cyan-700/50 text-cyan-400 text-[10px] font-mono px-2 py-0.5 rounded tracking-wide font-medium">
                P4 GROUND STATION
              </span>
              {activeMission && (
                <span className="bg-slate-800 text-slate-300 text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700">
                  {activeMission.mission_name} ({activeMission.status})
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              Autonomous GPS-Denied Navigation, Mission Management &amp; 3D Real-Time Analytics Station
            </p>
          </div>
        </div>

        {/* Global Telemetry & Frame Indicators */}
        <div className="flex items-center gap-2 sm:gap-3 font-mono text-xs">
          <div className="bg-slate-950 px-2.5 py-1 rounded border border-slate-800 flex items-center gap-1.5">
            <span className="text-slate-500 text-[10px] font-sans uppercase">Frame</span>
            <span className="font-bold text-slate-200">
              {currentFrame > 0 ? `#${currentFrame}` : "--"}
            </span>
          </div>

          <div className="bg-slate-950 px-2.5 py-1 rounded border border-slate-800 flex items-center gap-1.5">
            <span className="text-slate-500 text-[10px] font-sans uppercase">Sim Time</span>
            <span className="font-bold text-amber-400">
              {currentTimestamp > 0 ? `${currentTimestamp.toFixed(2)}s` : "--"}
            </span>
          </div>

          <div className="bg-slate-950 px-2.5 py-1 rounded border border-slate-800 flex items-center gap-2">
            <span className="text-slate-500 text-[10px] font-sans uppercase">Telemetry</span>
            <span className="flex items-center gap-1 text-[11px] font-semibold">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isTelemetryConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
                }`}
              />
              <span className={isTelemetryConnected ? "text-emerald-400" : "text-rose-400"}>
                {isTelemetryConnected ? "ONLINE" : "OFFLINE"}
              </span>
            </span>
          </div>
        </div>
      </header>

      {/* M6 Real Integration & Source Health Status Banner */}
      <div className="bg-slate-900/90 border border-slate-800/90 rounded-lg px-3 py-2 flex flex-wrap items-center justify-between gap-2 shadow-sm">
        <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold uppercase tracking-wider">
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span>Source Health:</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <SourceStatusBadge
            label="P1 Perception"
            icon={Eye}
            health={integratedState?.source_health?.p1}
            fallbackActive={!!perception}
          />
          <SourceStatusBadge
            label="P2 Simulation GT"
            icon={Layers}
            health={integratedState?.source_health?.p2}
            fallbackActive={!!groundTruth}
          />
          <SourceStatusBadge
            label="P3 Navigation"
            icon={NavIcon}
            health={integratedState?.source_health?.p3}
            fallbackActive={!!navigation}
          />
          <SourceStatusBadge
            label="P2 Camera"
            icon={Video}
            health={integratedState?.source_health?.camera}
            fallbackActive={isCameraConnected}
          />
        </div>
      </div>

      {/* Main Row: Live Camera (Left) + Interactive 3D Navigation (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5 items-stretch">
        <div className="min-h-[380px] lg:h-[440px] flex flex-col">
          <CameraStream
            imageSrc={imageSrc}
            isConnected={isCameraConnected}
            fps={cameraFps}
            frameCount={cameraFrames}
          />
        </div>

        <div className="min-h-[380px] lg:h-[440px] flex flex-col">
          <Navigation3DView
            telemetry={telemetry}
            groundTruth={groundTruth}
            mission={activeMission}
            trajectoryHistory={{
              estimated: liveEstimated.length > 0 ? liveEstimated : trajectoryHistory?.estimated ?? [],
              ground_truth: liveGroundTruth.length > 0 ? liveGroundTruth : trajectoryHistory?.ground_truth ?? [],
            }}
          />
        </div>
      </div>

      {/* Middle Operations Row: Mission Control + Analytics + Telemetry */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        <MissionControl
          activeMission={activeMission}
          onMissionCreated={(m) => setActiveMission(m)}
          onMissionStatusChange={(st) =>
            setActiveMission((prev) => (prev ? { ...prev, status: st as any } : prev))
          }
          apiBaseUrl={apiBaseUrl}
        />

        <AnalyticsCard analytics={analytics} />

        <div className="flex flex-col gap-3.5">
          <TelemetryCard telemetry={telemetry} isConnected={isTelemetryConnected} />
          <PoseComparisonCard groundTruth={groundTruth} navigation={navigation} />
        </div>
      </div>

      {/* Bottom Diagnostics Row: Scene Analysis + Event Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5">
        <div className="lg:col-span-6">
          <PerceptionCard perception={perception} />
        </div>
        <div className="lg:col-span-6">
          <EventLogCard logs={logs} syncStatus={integratedState?.sync_status} />
        </div>
      </div>
    </main>
  );
}
