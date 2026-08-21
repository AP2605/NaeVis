"use client";

import React, { useState, useEffect } from "react";
import { Activity, BarChart2, Compass, Gauge, TrendingUp, AlertCircle } from "lucide-react";
import { AnalyticsData } from "../types/telemetry";

interface AnalyticsCardProps {
  analytics: AnalyticsData | null;
}

interface ErrorDataPoint {
  time: string;
  error: number;
}

export function AnalyticsCard({ analytics }: AnalyticsCardProps) {
  const [errorHistory, setErrorHistory] = useState<ErrorDataPoint[]>([]);

  // Update real-time error history
  useEffect(() => {
    if (analytics?.localization_error?.current !== undefined && analytics.localization_error.current !== null) {
      const nowStr = new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setErrorHistory((prev) => [
        ...prev.slice(-29), // Keep latest 30 points
        { time: nowStr, error: analytics.localization_error.current! },
      ]);
    }
  }, [analytics?.localization_error?.current, analytics?.timestamp]);

  const loc = analytics?.localization_error;
  const ate = analytics?.ate;
  const rpe = analytics?.rpe;
  const drift = analytics?.drift;
  const orient = analytics?.orientation_error;
  const status = analytics?.synchronization_status || "INSUFFICIENT DATA";

  // Chart Dimensions & Scaling
  const maxErrorVal = errorHistory.length > 0 ? Math.max(...errorHistory.map((d) => d.error), 1.0) : 1.0;
  const chartHeight = 70;
  const chartWidth = 280;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5 shadow-lg flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
            Navigation Analytics & Evaluation
          </h3>
        </div>

        {/* Sync Status Badge */}
        <span
          className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold tracking-wide border ${
            status === "SYNCED"
              ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/50"
              : status === "PARTIAL"
              ? "bg-amber-950/80 text-amber-300 border-amber-500/50"
              : "bg-slate-800 text-slate-400 border-slate-700"
          }`}
        >
          {status}
        </span>
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {/* Current Euclidean Error */}
        <div className="bg-slate-950/80 border border-slate-800 rounded p-2 flex flex-col">
          <span className="text-[10px] text-slate-400 font-medium">3D Loc Error</span>
          <span className="text-base font-mono font-bold text-cyan-400">
            {loc?.current != null ? `${loc.current.toFixed(2)} m` : "--"}
          </span>
          <span className="text-[9px] text-slate-500 font-mono">
            {loc?.dx != null && loc?.dy != null
              ? `ΔX:${loc.dx > 0 ? "+" : ""}${loc.dx.toFixed(2)} ΔY:${loc.dy > 0 ? "+" : ""}${loc.dy.toFixed(2)}`
              : "Synchronizing..."}
          </span>
        </div>

        {/* ATE RMSE */}
        <div className="bg-slate-950/80 border border-slate-800 rounded p-2 flex flex-col">
          <span className="text-[10px] text-slate-400 font-medium">ATE RMSE</span>
          <span className="text-base font-mono font-bold text-slate-200">
            {ate?.rmse != null ? `${ate.rmse.toFixed(2)} m` : "--"}
          </span>
          <span className="text-[9px] text-slate-500 font-mono">
            {ate?.mean != null ? `Mean: ${ate.mean.toFixed(2)}m` : "No pairs"}
          </span>
        </div>

        {/* RPE RMSE */}
        <div className="bg-slate-950/80 border border-slate-800 rounded p-2 flex flex-col">
          <span className="text-[10px] text-slate-400 font-medium">RPE RMSE</span>
          <span className="text-base font-mono font-bold text-slate-200">
            {rpe?.rmse != null ? `${rpe.rmse.toFixed(3)} m` : "--"}
          </span>
          <span className="text-[9px] text-slate-500 font-mono">
            {rpe?.mean != null ? `Mean: ${rpe.mean.toFixed(3)}m` : "Step motion"}
          </span>
        </div>

        {/* Trajectory Drift */}
        <div className="bg-slate-950/80 border border-slate-800 rounded p-2 flex flex-col">
          <span className="text-[10px] text-slate-400 font-medium">Drift %</span>
          <span className="text-base font-mono font-bold text-amber-400">
            {drift?.percentage != null ? `${drift.percentage.toFixed(1)}%` : "--"}
          </span>
          <span className="text-[9px] text-slate-500 font-mono">
            {drift?.traveled_distance_m != null ? `Dist: ${drift.traveled_distance_m.toFixed(1)}m` : "--"}
          </span>
        </div>
      </div>

      {/* Secondary Metrics: Axis & Orientation Errors */}
      <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-950/50 border border-slate-800/60 rounded p-2">
        <div>
          <span className="text-slate-400 font-semibold block mb-1">Axis Residuals</span>
          <div className="flex justify-between text-slate-300 font-mono text-[10px]">
            <span>ΔX: <strong className="text-slate-100">{loc?.dx != null ? `${loc.dx > 0 ? "+" : ""}${loc.dx.toFixed(2)}m` : "--"}</strong></span>
            <span>ΔY: <strong className="text-slate-100">{loc?.dy != null ? `${loc.dy > 0 ? "+" : ""}${loc.dy.toFixed(2)}m` : "--"}</strong></span>
            <span>ΔZ: <strong className="text-slate-100">{loc?.dz != null ? `${loc.dz > 0 ? "+" : ""}${loc.dz.toFixed(2)}m` : "--"}</strong></span>
          </div>
        </div>

        <div>
          <span className="text-slate-400 font-semibold block mb-1">Attitude Errors</span>
          <div className="flex justify-between text-slate-300 font-mono text-[10px]">
            <span>Roll: <strong className="text-slate-100">{orient?.roll != null ? `${orient.roll > 0 ? "+" : ""}${orient.roll.toFixed(1)}°` : "--"}</strong></span>
            <span>Pitch: <strong className="text-slate-100">{orient?.pitch != null ? `${orient.pitch > 0 ? "+" : ""}${orient.pitch.toFixed(1)}°` : "--"}</strong></span>
            <span>Yaw: <strong className="text-slate-100">{orient?.yaw != null ? `${orient.yaw > 0 ? "+" : ""}${orient.yaw.toFixed(1)}°` : "--"}</strong></span>
          </div>
        </div>
      </div>

      {/* Real-time Localization Error vs Time Chart */}
      <div className="bg-slate-950/80 border border-slate-800 rounded p-2 flex flex-col gap-1">
        <div className="flex justify-between items-center text-[10px] text-slate-400">
          <span className="font-semibold text-slate-300 flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-cyan-400" />
            3D Localization Error vs Time (meters)
          </span>
          <span className="font-mono text-slate-500">Max: {maxErrorVal.toFixed(2)}m</span>
        </div>

        {errorHistory.length < 2 ? (
          <div className="h-[70px] flex items-center justify-center text-[11px] text-slate-500 italic">
            Awaiting synchronized flight telemetry frames...
          </div>
        ) : (
          <div className="relative w-full h-[70px] pt-1">
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-full overflow-visible">
              {/* Horizontal Grid lines */}
              <line x1="0" y1="0" x2={chartWidth} y2="0" stroke="#334155" strokeDasharray="3 3" strokeWidth="0.5" />
              <line x1="0" y1={chartHeight / 2} x2={chartWidth} y2={chartHeight / 2} stroke="#1e293b" strokeDasharray="3 3" strokeWidth="0.5" />
              <line x1="0" y1={chartHeight} x2={chartWidth} y2={chartHeight} stroke="#334155" strokeWidth="0.8" />

              {/* Error Line Path */}
              {(() => {
                const stepX = chartWidth / (errorHistory.length - 1);
                const pointsSvg = errorHistory
                  .map((d, idx) => {
                    const x = idx * stepX;
                    const y = chartHeight - (d.error / maxErrorVal) * (chartHeight - 8);
                    return `${x},${y}`;
                  })
                  .join(" ");
                return (
                  <>
                    <polyline fill="none" stroke="#06b6d4" strokeWidth="1.8" strokeLinecap="round" points={pointsSvg} />
                    {/* Area fill */}
                    <polygon
                      fill="url(#cyanGradient)"
                      points={`0,${chartHeight} ${pointsSvg} ${chartWidth},${chartHeight}`}
                      opacity="0.2"
                    />
                  </>
                );
              })()}

              <defs>
                <linearGradient id="cyanGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#06b6d4" />
                  <stop offset="100%" stopColor="#06b6d4" stopOpacity="0" />
                </linearGradient>
              </defs>
            </svg>
          </div>
        )}
      </div>
    </div>
  );
}
