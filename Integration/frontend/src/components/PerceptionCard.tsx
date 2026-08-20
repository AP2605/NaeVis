"use client";

import React from "react";
import { Eye, MapPin, Layers, Crosshair, AlertCircle, Compass, ShieldAlert, CheckCircle } from "lucide-react";
import { P1VisionResult } from "../types/telemetry";

interface PerceptionProps {
  perception: P1VisionResult | null;
}

export const PerceptionCard: React.FC<PerceptionProps> = ({ perception }) => {
  return (
    <div className="bg-ops-panel border border-ops-border rounded-lg p-3.5 sm:p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-ops-border pb-2.5">
        <div className="flex items-center gap-2">
          <Eye className="w-4 h-4 text-ops-accent" />
          <h2 className="font-semibold text-ops-text text-xs tracking-wider uppercase">
            Scene Analysis
          </h2>
        </div>
        <span className="text-[11px] font-mono text-ops-textDim">
          Frame: {perception?.frame_id !== undefined ? `#${perception.frame_id}` : "--"}
        </span>
      </div>

      {perception ? (
        <div className="space-y-2.5 text-xs">
          {/* Top row: Terrain + Visual Location */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {/* Terrain Analysis */}
            <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border">
              <div className="flex items-center gap-1.5 text-ops-accent font-medium mb-1 text-[11px] uppercase tracking-wide">
                <Layers className="w-3.5 h-3.5" />
                <span>Terrain</span>
              </div>
              <div className="text-sm font-semibold capitalize text-ops-text">
                {perception.terrain?.terrain_type || "Unknown"}
              </div>
              <div className="text-[11px] text-ops-textMuted font-mono mt-0.5 flex items-center gap-2">
                <span>Conf: {perception.terrain ? `${(perception.terrain.confidence * 100).toFixed(0)}%` : "--"}</span>
                <span className="text-ops-borderLight">|</span>
                <span>Roughness: {perception.terrain?.roughness?.toFixed(2) ?? "0.00"}</span>
              </div>
            </div>

            {/* Visual Location / Place Recognition */}
            <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border">
              <div className="flex items-center gap-1.5 text-ops-info font-medium mb-1 text-[11px] uppercase tracking-wide">
                <MapPin className="w-3.5 h-3.5" />
                <span>Visual Location</span>
              </div>
              <div className="text-sm font-semibold text-ops-text truncate">
                {perception.place_recognition?.match_found
                  ? perception.place_recognition.location_id || "Identified Zone"
                  : "Scanning environment..."}
              </div>
              <div className="text-[11px] text-ops-textMuted font-mono mt-0.5">
                Match Score:{" "}
                <span className={perception.place_recognition?.match_found ? "text-ops-success font-medium" : "text-ops-textDim"}>
                  {perception.place_recognition?.similarity_score
                    ? `${(perception.place_recognition.similarity_score * 100).toFixed(0)}%`
                    : "--"}
                </span>
              </div>
            </div>
          </div>

          {/* Detected Landmarks */}
          <div className="bg-ops-subpanel p-2.5 rounded-md border border-ops-border">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5 text-ops-success font-medium text-[11px] uppercase tracking-wide">
                <Crosshair className="w-3.5 h-3.5" />
                <span>Detected Landmarks ({perception.landmarks?.length ?? 0})</span>
              </div>
            </div>
            {perception.landmarks && perception.landmarks.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-24 overflow-y-auto pr-1">
                {perception.landmarks.map((lm, idx) => (
                  <div
                    key={idx}
                    className="bg-ops-card px-2 py-1 rounded border border-ops-border/60 text-[11px] font-mono"
                  >
                    <div className="text-ops-text font-medium truncate flex items-center justify-between">
                      <span>{lm.label}</span>
                      <span className="text-ops-textDim text-[10px]">#{lm.landmark_id}</span>
                    </div>
                    {lm.estimated_relative_pos && (
                      <div className="text-ops-textDim text-[10px]">
                        Rel: ({lm.estimated_relative_pos.x.toFixed(1)}, {lm.estimated_relative_pos.y.toFixed(1)}, {lm.estimated_relative_pos.z.toFixed(1)}) m
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-ops-textDim text-[11px] italic py-1 font-mono">
                No prominent landmarks detected in current FOV
              </div>
            )}
          </div>

          {/* Optional: Mission Awareness / Terrain Match (if populated) */}
          {(perception.terrain_match || perception.mission_awareness) && (
            <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
              {perception.terrain_match && (
                <div className="bg-ops-subpanel p-2 rounded border border-ops-border flex items-center justify-between">
                  <span className="text-ops-textDim">Terrain Match:</span>
                  <span className={perception.terrain_match.matched ? "text-ops-success font-semibold" : "text-ops-textDim"}>
                    {perception.terrain_match.matched ? `${((perception.terrain_match.correlation_score ?? 0.9) * 100).toFixed(0)}%` : "None"}
                  </span>
                </div>
              )}
              {perception.mission_awareness && (
                <div className="bg-ops-subpanel p-2 rounded border border-ops-border flex items-center justify-between">
                  <span className="text-ops-textDim">Landing Zone:</span>
                  <span className={perception.mission_awareness.landing_zone_viable ? "text-ops-success font-semibold" : "text-ops-warning font-semibold"}>
                    {perception.mission_awareness.landing_zone_viable ? "Viable" : "Caution"}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Segmentation & System Diagnostics */}
          <div className="flex flex-wrap items-center justify-between bg-ops-subpanel px-2.5 py-1.5 rounded-md border border-ops-border text-[11px] text-ops-textDim font-mono gap-2">
            <div>
              Classes: <span className="text-ops-textMuted">{perception.segmentation?.classes?.join(", ") || "None"}</span>
            </div>
            <div>
              Inference Latency:{" "}
              <span className="text-ops-textMuted">
                {perception.system?.inference_time_ms ?? 0} ms ({perception.system?.device ?? "cpu"})
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-6 flex flex-col items-center justify-center text-ops-textDim text-xs gap-2">
          <AlertCircle className="w-5 h-5 text-ops-textDim/70" />
          <span className="font-mono text-[11px]">Awaiting scene analysis telemetry...</span>
        </div>
      )}
    </div>
  );
};

