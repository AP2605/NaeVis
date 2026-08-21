"use client";

import React, { useState } from "react";
import { CameraStream } from "../components/CameraStream";
import { PoseComparisonCard } from "../components/PoseComparisonCard";
import { PerceptionCard } from "../components/PerceptionCard";
import { TelemetryCard } from "../components/TelemetryCard";
import { EventLogCard } from "../components/EventLogCard";
import { useTelemetryWebSocket } from "../hooks/useTelemetryWebSocket";
import { useCameraWebSocket } from "../hooks/useCameraWebSocket";
import { Compass, Radio, ShieldCheck, Activity } from "lucide-react";

export default function DashboardPage() {
  const wsTelemetryUrl = "ws://localhost:8000/ws/telemetry";
  const wsCameraUrl = "ws://localhost:8000/ws/camera?role=viewer";

  const {
    isConnected: isTelemetryConnected,
    telemetry,
    integratedState,
    groundTruth,
    navigation,
    perception,
    logs,
  } = useTelemetryWebSocket(wsTelemetryUrl);

  const {
    isConnected: isCameraConnected,
    imageSrc,
    fps: cameraFps,
    frameCount: cameraFrames,
  } = useCameraWebSocket(wsCameraUrl);

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
    <main className="min-h-screen w-full px-3.5 sm:px-5 lg:px-6 py-3.5 flex flex-col gap-3.5 bg-ops-bg text-ops-text">
      {/* Top Header Bar */}
      <header className="bg-ops-panel border border-ops-border rounded-lg p-3 sm:p-3.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-ops-card border border-ops-border text-ops-accent">
            <Compass className="w-5 h-5 stroke-[2]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold tracking-tight text-ops-text">
                NaeVis
              </h1>
              <span className="bg-ops-accentBg border border-ops-accent/30 text-ops-accent text-[10px] font-mono px-2 py-0.5 rounded tracking-wide font-medium">
                MISSION MONITOR
              </span>
            </div>
            <p className="text-[11px] text-ops-textMuted hidden sm:block">
              Autonomous GPS-Denied Navigation &amp; Multi-Sensor Perception Operations Station
            </p>
          </div>
        </div>

        {/* Global Sync & Telemetry Indicators */}
        <div className="flex items-center gap-2 sm:gap-3 font-mono text-xs">
          <div className="bg-ops-subpanel px-2.5 py-1 rounded border border-ops-border flex items-center gap-1.5">
            <span className="text-ops-textDim text-[10px] font-sans uppercase">Frame</span>
            <span className="font-bold text-ops-text">
              {currentFrame > 0 ? `#${currentFrame}` : "--"}
            </span>
          </div>

          <div className="bg-ops-subpanel px-2.5 py-1 rounded border border-ops-border flex items-center gap-1.5">
            <span className="text-ops-textDim text-[10px] font-sans uppercase">Time</span>
            <span className="font-bold text-ops-warning">
              {currentTimestamp > 0 ? `${currentTimestamp.toFixed(2)}s` : "--"}
            </span>
          </div>

          <div className="bg-ops-subpanel px-2.5 py-1 rounded border border-ops-border flex items-center gap-2">
            <span className="text-ops-textDim text-[10px] font-sans uppercase">Telemetry</span>
            <span className="flex items-center gap-1 text-[11px] font-semibold">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isTelemetryConnected ? "bg-ops-success animate-pulse" : "bg-ops-critical"
                }`}
              />
              <span
                className={
                  isTelemetryConnected ? "text-ops-success" : "text-ops-critical"
                }
              >
                {isTelemetryConnected ? "ONLINE" : "OFFLINE"}
              </span>
            </span>
          </div>
        </div>
      </header>

      {/* Primary Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5">
        {/* Left Column: Live Camera + State Comparison */}
        <div className="lg:col-span-7 flex flex-col gap-3.5">
          <CameraStream
            imageSrc={imageSrc}
            isConnected={isCameraConnected}
            fps={cameraFps}
            frameCount={cameraFrames}
          />
          <PoseComparisonCard
            groundTruth={groundTruth}
            navigation={navigation}
          />
        </div>

        {/* Right Column: Flight Telemetry + Scene Analysis + Event Logs */}
        <div className="lg:col-span-5 flex flex-col gap-3.5">
          <TelemetryCard
            telemetry={telemetry}
            isConnected={isTelemetryConnected}
          />
          <PerceptionCard perception={perception} />
          <EventLogCard
            logs={logs}
            syncStatus={integratedState?.sync_status}
          />
        </div>
      </div>
    </main>
  );
}

