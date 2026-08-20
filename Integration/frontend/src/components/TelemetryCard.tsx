"use client";

import React from "react";
import { Activity, Gauge, Compass, ShieldCheck } from "lucide-react";
import { Telemetry } from "../types/telemetry";

interface TelemetryCardProps {
  telemetry: Telemetry | null;
  isConnected: boolean;
}

export const TelemetryCard: React.FC<TelemetryCardProps> = ({
  telemetry,
  isConnected,
}) => {
  return (
    <div className="bg-ops-panel border border-ops-border rounded-lg p-3.5 sm:p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-ops-border pb-2.5">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-ops-accent" />
          <h2 className="font-semibold text-ops-text text-xs tracking-wider uppercase">
            Flight Telemetry
          </h2>
        </div>
        <div className="flex items-center gap-2.5 font-mono text-[11px]">
          <span className="text-ops-textDim">
            {telemetry ? new Date(telemetry.timestamp).toLocaleTimeString() : "--:--:--"}
          </span>
          <div className="flex items-center gap-1.5">
            {isConnected ? (
              <span className="text-ops-success bg-ops-successBg border border-ops-success/30 px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse" />
                STREAM ACTIVE
              </span>
            ) : (
              <span className="text-ops-critical bg-ops-criticalBg border border-ops-critical/30 px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-ops-critical" />
                OFFLINE
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Grid of Key Telemetry Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono text-xs">
        <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border flex flex-col justify-between">
          <span className="text-ops-textDim block text-[10px] font-sans uppercase">Altitude (AGL)</span>
          <span className="text-sm sm:text-base font-semibold text-ops-text mt-1">
            {telemetry ? `${telemetry.z.toFixed(2)} m` : "--"}
          </span>
        </div>

        <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border flex flex-col justify-between">
          <span className="text-ops-textDim block text-[10px] font-sans uppercase">Ground Velocity</span>
          <span className="text-sm sm:text-base font-semibold text-ops-text mt-1">
            {telemetry ? `${telemetry.velocity.toFixed(2)} m/s` : "--"}
          </span>
        </div>

        <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border flex flex-col justify-between">
          <span className="text-ops-textDim block text-[10px] font-sans uppercase">Heading (Yaw)</span>
          <span className="text-sm sm:text-base font-semibold text-ops-text mt-1">
            {telemetry ? `${telemetry.yaw.toFixed(1)}°` : "--"}
          </span>
        </div>

        <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border flex flex-col justify-between">
          <span className="text-ops-textDim block text-[10px] font-sans uppercase">Localization Conf</span>
          <span className="text-sm sm:text-base font-semibold text-ops-success mt-1">
            {telemetry ? `${(telemetry.confidence * 100).toFixed(0)}%` : "--"}
          </span>
        </div>
      </div>

      {/* Position Coordinates Bar */}
      <div className="bg-ops-subpanel px-3 py-2 rounded-md border border-ops-border flex flex-wrap items-center justify-between text-xs font-mono text-ops-textMuted gap-2">
        <span className="text-ops-textDim text-[11px] font-sans uppercase">Local Frame Coordinates:</span>
        <div className="flex items-center gap-3">
          <span>X: <span className="text-ops-text font-semibold">{telemetry ? telemetry.x.toFixed(2) : "--"} m</span></span>
          <span className="text-ops-borderLight">|</span>
          <span>Y: <span className="text-ops-text font-semibold">{telemetry ? telemetry.y.toFixed(2) : "--"} m</span></span>
          <span className="text-ops-borderLight">|</span>
          <span>Z: <span className="text-ops-text font-semibold">{telemetry ? telemetry.z.toFixed(2) : "--"} m</span></span>
        </div>
      </div>
    </div>
  );
};

