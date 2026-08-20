"use client";

import React from "react";
import { Compass, Navigation, Activity, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { NavigationStatePacket, SimulationGroundTruthPacket } from "../types/telemetry";

interface PoseComparisonProps {
  groundTruth: SimulationGroundTruthPacket | null;
  navigation: NavigationStatePacket | null;
}

export const PoseComparisonCard: React.FC<PoseComparisonProps> = ({
  groundTruth,
  navigation,
}) => {
  // Compute Euclidean distance delta if both are available
  let posError: number | null = null;
  if (groundTruth?.position && navigation?.estimated_pose) {
    const dx = groundTruth.position.x - navigation.estimated_pose.x;
    const dy = groundTruth.position.y - navigation.estimated_pose.y;
    const dz = groundTruth.position.z - navigation.estimated_pose.z;
    posError = Math.sqrt(dx * dx + dy * dy + dz * dz);
  }

  const getTrackingBadge = (state?: string) => {
    switch (state) {
      case "TRACKING_GOOD":
        return {
          icon: <CheckCircle2 className="w-3.5 h-3.5" />,
          label: "TRACKING GOOD",
          className: "bg-ops-successBg text-ops-success border-ops-success/30",
        };
      case "TRACKING_DEGRADED":
        return {
          icon: <AlertTriangle className="w-3.5 h-3.5" />,
          label: "TRACKING DEGRADED",
          className: "bg-ops-warningBg text-ops-warning border-ops-warning/30",
        };
      case "TRACKING_LOST":
        return {
          icon: <XCircle className="w-3.5 h-3.5" />,
          label: "TRACKING LOST",
          className: "bg-ops-criticalBg text-ops-critical border-ops-critical/30",
        };
      default:
        return {
          icon: <Activity className="w-3.5 h-3.5" />,
          label: state || "STANDBY",
          className: "bg-ops-subpanel text-ops-textDim border-ops-border",
        };
    }
  };

  const trackingInfo = getTrackingBadge(navigation?.tracking_state);

  return (
    <div className="bg-ops-panel border border-ops-border rounded-lg p-3.5 sm:p-4 flex flex-col gap-3.5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-ops-border pb-2.5">
        <div className="flex items-center gap-2">
          <Navigation className="w-4 h-4 text-ops-accent" />
          <h2 className="font-semibold text-ops-text text-xs tracking-wider uppercase">
            State Comparison: Reference vs Navigation Estimate
          </h2>
        </div>
        {navigation && (
          <span
            className={`text-[11px] px-2.5 py-0.5 rounded border font-mono font-medium flex items-center gap-1.5 ${trackingInfo.className}`}
          >
            {trackingInfo.icon}
            {trackingInfo.label}
          </span>
        )}
      </div>

      {/* Side by Side Pose Data */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Reference / Ground Truth */}
        <div className="bg-ops-subpanel border border-ops-border rounded-md p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs font-semibold mb-2">
            <span className="text-ops-warning flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-ops-warning" />
              GROUND TRUTH (REFERENCE)
            </span>
            <span className="font-mono text-[11px] text-ops-textDim">
              Frame: {groundTruth?.frame_id !== undefined ? `#${groundTruth.frame_id}` : "--"}
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            {/* Position */}
            <div className="grid grid-cols-3 gap-2 bg-ops-card/90 border border-ops-border/60 p-2 rounded">
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">X (Ref)</span>
                <span className="text-ops-text font-medium text-xs sm:text-sm">
                  {groundTruth ? `${groundTruth.position.x.toFixed(2)} m` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Y (Ref)</span>
                <span className="text-ops-text font-medium text-xs sm:text-sm">
                  {groundTruth ? `${groundTruth.position.y.toFixed(2)} m` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Z (Ref)</span>
                <span className="text-ops-text font-medium text-xs sm:text-sm">
                  {groundTruth ? `${groundTruth.position.z.toFixed(2)} m` : "--"}
                </span>
              </div>
            </div>

            {/* Orientation */}
            <div className="grid grid-cols-3 gap-2 bg-ops-card/90 border border-ops-border/60 p-2 rounded">
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Roll</span>
                <span className="text-ops-textMuted text-xs">
                  {groundTruth ? `${groundTruth.orientation.roll.toFixed(1)}°` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Pitch</span>
                <span className="text-ops-textMuted text-xs">
                  {groundTruth ? `${groundTruth.orientation.pitch.toFixed(1)}°` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Yaw</span>
                <span className="text-ops-textMuted text-xs">
                  {groundTruth ? `${groundTruth.orientation.yaw.toFixed(1)}°` : "--"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Estimate */}
        <div className="bg-ops-subpanel border border-ops-border rounded-md p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs font-semibold mb-2">
            <span className="text-ops-accent flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-ops-accent" />
              NAVIGATION ESTIMATE (INS / VIO)
            </span>
            <span className="font-mono text-[11px] text-ops-textDim">
              Frame: {navigation?.frame_id !== undefined ? `#${navigation.frame_id}` : "--"}
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            {/* Position */}
            <div className="grid grid-cols-3 gap-2 bg-ops-card/90 border border-ops-border/60 p-2 rounded">
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">X (Est)</span>
                <span className="text-ops-text font-medium text-xs sm:text-sm">
                  {navigation ? `${navigation.estimated_pose.x.toFixed(2)} m` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Y (Est)</span>
                <span className="text-ops-text font-medium text-xs sm:text-sm">
                  {navigation ? `${navigation.estimated_pose.y.toFixed(2)} m` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Z (Est)</span>
                <span className="text-ops-text font-medium text-xs sm:text-sm">
                  {navigation ? `${navigation.estimated_pose.z.toFixed(2)} m` : "--"}
                </span>
              </div>
            </div>

            {/* Orientation */}
            <div className="grid grid-cols-3 gap-2 bg-ops-card/90 border border-ops-border/60 p-2 rounded">
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Roll</span>
                <span className="text-ops-textMuted text-xs">
                  {navigation ? `${navigation.estimated_pose.roll.toFixed(1)}°` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Pitch</span>
                <span className="text-ops-textMuted text-xs">
                  {navigation ? `${navigation.estimated_pose.pitch.toFixed(1)}°` : "--"}
                </span>
              </div>
              <div>
                <span className="text-ops-textDim block text-[10px] uppercase font-sans">Yaw</span>
                <span className="text-ops-textMuted text-xs">
                  {navigation ? `${navigation.estimated_pose.yaw.toFixed(1)}°` : "--"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error & Evaluation Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-ops-subpanel p-2.5 rounded-md border border-ops-border text-xs">
        <div>
          <span className="text-ops-textDim block text-[10px] uppercase font-sans">Position Delta (Δ)</span>
          <span className="font-mono font-semibold text-ops-warning text-xs sm:text-sm">
            {posError !== null ? `${posError.toFixed(3)} m` : "--"}
          </span>
        </div>
        <div>
          <span className="text-ops-textDim block text-[10px] uppercase font-sans">Localization Confidence</span>
          <span className="font-mono font-semibold text-ops-success text-xs sm:text-sm">
            {navigation ? `${(navigation.confidence * 100).toFixed(0)}%` : "--"}
          </span>
        </div>
        <div>
          <span className="text-ops-textDim block text-[10px] uppercase font-sans">Ground Velocity</span>
          <span className="font-mono font-semibold text-ops-text text-xs sm:text-sm">
            {navigation
              ? `${Math.sqrt(
                  navigation.velocity.x ** 2 +
                    navigation.velocity.y ** 2 +
                    navigation.velocity.z ** 2
                ).toFixed(2)} m/s`
              : "--"}
          </span>
        </div>
        <div>
          <span className="text-ops-textDim block text-[10px] uppercase font-sans">Processing Latency</span>
          <span className="font-mono font-semibold text-ops-textMuted text-xs sm:text-sm">
            {navigation?.processing_time_ms !== undefined
              ? `${navigation.processing_time_ms} ms`
              : "--"}
          </span>
        </div>
      </div>
    </div>
  );
};

