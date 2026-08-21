"use client";

import React from "react";
import { Camera, Video, VideoOff } from "lucide-react";

interface CameraStreamProps {
  imageSrc: string | null;
  isConnected: boolean;
  fps: number;
  frameCount: number;
}

export const CameraStream: React.FC<CameraStreamProps> = ({
  imageSrc,
  isConnected,
  fps,
  frameCount,
}) => {
  return (
    <div className="bg-ops-panel border border-ops-border rounded-lg overflow-hidden flex flex-col">
      {/* Header */}
      <div className="px-3.5 py-2.5 bg-ops-card border-b border-ops-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Camera className="w-4 h-4 text-ops-accent" />
          <h2 className="font-semibold text-ops-text text-xs tracking-wider uppercase">
            Live Camera
          </h2>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-ops-subpanel border border-ops-border text-ops-success font-medium">
            {fps} FPS
          </span>
          <span className="text-[11px] font-mono text-ops-textMuted hidden sm:inline">
            Frames: {frameCount}
          </span>
          <div className="flex items-center gap-1.5 text-xs font-mono">
            {isConnected ? (
              <span className="flex items-center gap-1 text-[11px] text-ops-success bg-ops-successBg border border-ops-success/30 px-2 py-0.5 rounded">
                <span className="w-1.5 h-1.5 rounded-full bg-ops-success animate-pulse" />
                STREAM ACTIVE
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] text-ops-critical bg-ops-criticalBg border border-ops-critical/30 px-2 py-0.5 rounded">
                <span className="w-1.5 h-1.5 rounded-full bg-ops-critical" />
                NO SIGNAL
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Video Display Area */}
      <div className="relative aspect-[16/10] sm:aspect-video bg-[#0c0d0f] flex items-center justify-center overflow-hidden">
        {imageSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageSrc}
            alt="Live Optical Feed"
            className="w-full h-full object-contain select-none"
          />
        ) : (
          <div className="flex flex-col items-center justify-center gap-2.5 text-ops-textDim p-6 text-center">
            <VideoOff className="w-8 h-8 text-ops-textDim stroke-[1.5]" />
            <div className="text-xs font-medium text-ops-textMuted">
              Awaiting Optical Stream (/ws/camera)
            </div>
            <div className="text-[11px] text-ops-textDim font-mono max-w-xs">
              Direct binary MJPEG feed will render when bridge or simulation stream is active
            </div>
          </div>
        )}

        {/* Technical HUD Overlay Badges */}
        <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5 pointer-events-none">
          <div className="bg-ops-bg/85 backdrop-blur-sm border border-ops-border/80 rounded px-1.5 py-0.5 text-[10px] font-mono text-ops-textMuted tracking-tight">
            OPTICAL SENSOR 01
          </div>
          {imageSrc && (
            <div className="bg-ops-bg/85 backdrop-blur-sm border border-ops-accent/40 rounded px-1.5 py-0.5 text-[10px] font-mono text-ops-accent font-medium tracking-tight">
              LIVE
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

