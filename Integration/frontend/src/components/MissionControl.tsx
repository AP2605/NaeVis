"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  Flag,
  MapPin,
  Navigation,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Send,
  Trash2,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import { Mission, MissionProgress, Position3D, Waypoint } from "../types/telemetry";

interface MissionControlProps {
  activeMission: Mission | null;
  onMissionCreated: (mission: Mission) => void;
  onMissionStatusChange: (status: string) => void;
  apiBaseUrl?: string;
}

interface WaypointInput {
  x: string;
  y: string;
  z: string;
  name?: string;
}

export function MissionControl({
  activeMission,
  onMissionCreated,
  onMissionStatusChange,
  apiBaseUrl = "http://localhost:8000",
}: MissionControlProps) {
  const [missionName, setMissionName] = useState("Autonomous Survey Alpha");
  const [source, setSource] = useState<{ x: string; y: string; z: string }>({
    x: "0.0",
    y: "0.0",
    z: "10.0",
  });
  const [destination, setDestination] = useState<{ x: string; y: string; z: string }>({
    x: "100.0",
    y: "50.0",
    z: "20.0",
  });
  const [waypoints, setWaypoints] = useState<WaypointInput[]>([
    { x: "20.0", y: "10.0", z: "15.0", name: "WP-1" },
    { x: "40.0", y: "30.0", z: "18.0", name: "WP-2" },
    { x: "70.0", y: "40.0", z: "20.0", name: "WP-3" },
  ]);

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const addWaypoint = () => {
    const lastWp = waypoints.length > 0 ? waypoints[waypoints.length - 1] : { x: source.x, y: source.y, z: source.z };
    const nextX = (parseFloat(lastWp.x || "0") + 20.0).toFixed(1);
    const nextY = (parseFloat(lastWp.y || "0") + 10.0).toFixed(1);
    const nextZ = (parseFloat(lastWp.z || "10")).toFixed(1);
    setWaypoints((prev) => [
      ...prev,
      { x: nextX, y: nextY, z: nextZ, name: `WP-${prev.length + 1}` },
    ]);
  };

  const removeWaypoint = (index: number) => {
    setWaypoints((prev) => prev.filter((_, idx) => idx !== index));
  };

  const updateWaypoint = (index: number, field: keyof WaypointInput, value: string) => {
    setWaypoints((prev) =>
      prev.map((wp, idx) => (idx === index ? { ...wp, [field]: value } : wp))
    );
  };

  const handleCreateMission = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const srcX = parseFloat(source.x);
      const srcY = parseFloat(source.y);
      const srcZ = parseFloat(source.z);
      const dstX = parseFloat(destination.x);
      const dstY = parseFloat(destination.y);
      const dstZ = parseFloat(destination.z);

      if (isNaN(srcX) || isNaN(srcY) || isNaN(srcZ) || isNaN(dstX) || isNaN(dstY) || isNaN(dstZ)) {
        throw new Error("Source and Destination coordinates must be valid numbers");
      }

      const parsedWaypoints = waypoints.map((w, idx) => {
        const x = parseFloat(w.x);
        const y = parseFloat(w.y);
        const z = parseFloat(w.z);
        if (isNaN(x) || isNaN(y) || isNaN(z)) {
          throw new Error(`Waypoint #${idx + 1} contains invalid numeric coordinates`);
        }
        return { x, y, z, name: w.name || `WP-${idx + 1}` };
      });

      const payload = {
        mission_name: missionName.trim() || "Autonomous Mission",
        source: { x: srcX, y: srcY, z: srcZ },
        destination: { x: dstX, y: dstY, z: dstZ },
        waypoints: parsedWaypoints,
        coordinate_frame: "BLENDER_LOCAL",
      };

      const res = await fetch(`${apiBaseUrl}/api/v1/missions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || `Failed to create mission (HTTP ${res.status})`);
      }

      const created: Mission = await res.json();
      onMissionCreated(created);
      setSuccessMessage(`Mission created successfully (${created.mission_id.substring(0, 8)})`);
    } catch (err: any) {
      setErrorMessage(err.message || "Error creating mission");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (action: "start" | "pause" | "resume" | "cancel") => {
    if (!activeMission) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${apiBaseUrl}/api/v1/missions/${activeMission.mission_id}/${action}`, {
        method: "POST",
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || `Action '${action}' failed`);
      }
      const updated: Mission = await res.json();
      onMissionCreated(updated);
      onMissionStatusChange(updated.status);
    } catch (err: any) {
      setErrorMessage(err.message || `Failed to execute ${action}`);
    } finally {
      setIsLoading(false);
    }
  };

  const status = activeMission?.status ?? "DRAFT";
  const isRunning = status === "ACTIVE";
  const isPaused = status === "PAUSED";

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5 shadow-lg flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Navigation className="w-4 h-4 text-emerald-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
            Mission Control & Waypoints
          </h3>
        </div>

        {/* Status Badge */}
        <span
          className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold tracking-wide uppercase border ${
            status === "ACTIVE"
              ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/50 animate-pulse"
              : status === "PAUSED"
              ? "bg-amber-950/80 text-amber-300 border-amber-500/50"
              : status === "COMPLETED"
              ? "bg-cyan-950/80 text-cyan-300 border-cyan-500/50"
              : status === "CANCELLED"
              ? "bg-rose-950/80 text-rose-300 border-rose-500/50"
              : "bg-slate-800 text-slate-300 border-slate-700"
          }`}
        >
          {status}
        </span>
      </div>

      {/* Alerts */}
      {errorMessage && (
        <div className="bg-rose-950/80 border border-rose-600/50 text-rose-300 text-[11px] p-2 rounded flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}
      {successMessage && (
        <div className="bg-emerald-950/80 border border-emerald-600/50 text-emerald-300 text-[11px] p-2 rounded flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Mission Name Input */}
      <div>
        <label className="text-[11px] text-slate-400 font-medium block mb-1">Mission Identifier</label>
        <input
          type="text"
          value={missionName}
          onChange={(e) => setMissionName(e.target.value)}
          disabled={isRunning}
          className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 disabled:opacity-60"
        />
      </div>

      {/* Source Coordinates */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded p-2">
        <div className="flex items-center gap-1 text-[11px] text-emerald-400 font-semibold mb-1">
          <MapPin className="w-3 h-3" />
          SOURCE (Simulation Origin)
        </div>
        <div className="grid grid-cols-3 gap-1.5">
          {["x", "y", "z"].map((axis) => (
            <div key={axis} className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded px-1.5 py-0.5">
              <span className="text-[10px] text-slate-500 uppercase font-mono">{axis}:</span>
              <input
                type="text"
                value={(source as any)[axis]}
                onChange={(e) => setSource({ ...source, [axis]: e.target.value })}
                disabled={isRunning}
                className="w-full bg-transparent text-xs text-slate-200 font-mono focus:outline-none disabled:opacity-60"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Intermediate Waypoint List */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded p-2 flex flex-col gap-1.5 max-h-[160px] overflow-y-auto">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-slate-400 font-semibold">Intermediate Waypoints ({waypoints.length})</span>
          <button
            type="button"
            onClick={addWaypoint}
            disabled={isRunning}
            className="text-[10px] bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 px-1.5 py-0.5 rounded flex items-center gap-1 transition-colors disabled:opacity-50"
          >
            <Plus className="w-3 h-3" /> Add WP
          </button>
        </div>

        {waypoints.length === 0 ? (
          <p className="text-[11px] text-slate-500 italic py-1 text-center">
            Direct mission (0 intermediate waypoints)
          </p>
        ) : (
          waypoints.map((wp, idx) => (
            <div key={idx} className="flex items-center gap-1 bg-slate-900 border border-slate-800/80 rounded p-1 text-xs">
              <span className="text-[10px] font-mono text-cyan-400 font-bold w-7">#{idx + 1}</span>
              {["x", "y", "z"].map((axis) => (
                <div key={axis} className="flex items-center gap-0.5 flex-1 bg-slate-950 border border-slate-800 rounded px-1 py-0.5">
                  <span className="text-[9px] text-slate-500 uppercase font-mono">{axis}</span>
                  <input
                    type="text"
                    value={(wp as any)[axis]}
                    onChange={(e) => updateWaypoint(idx, axis as any, e.target.value)}
                    disabled={isRunning}
                    className="w-full bg-transparent text-[11px] text-slate-200 font-mono focus:outline-none"
                  />
                </div>
              ))}
              {!isRunning && (
                <button
                  type="button"
                  onClick={() => removeWaypoint(idx)}
                  className="text-slate-500 hover:text-rose-400 p-0.5"
                  title="Remove waypoint"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              )}
            </div>
          ))
        )}
      </div>

      {/* Destination Coordinates */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded p-2">
        <div className="flex items-center gap-1 text-[11px] text-amber-400 font-semibold mb-1">
          <Flag className="w-3 h-3" />
          DESTINATION (Target)
        </div>
        <div className="grid grid-cols-3 gap-1.5">
          {["x", "y", "z"].map((axis) => (
            <div key={axis} className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded px-1.5 py-0.5">
              <span className="text-[10px] text-slate-500 uppercase font-mono">{axis}:</span>
              <input
                type="text"
                value={(destination as any)[axis]}
                onChange={(e) => setDestination({ ...destination, [axis]: e.target.value })}
                disabled={isRunning}
                className="w-full bg-transparent text-xs text-slate-200 font-mono focus:outline-none disabled:opacity-60"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Mission Progress Bar (if active) */}
      {activeMission?.progress && (
        <div className="bg-slate-950/90 border border-slate-800 rounded p-2 flex flex-col gap-1">
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>Waypoint {activeMission.progress.current_waypoint_index + 1} of {activeMission.progress.total_waypoints + 1}</span>
            <span className="font-mono text-cyan-400 font-bold">{activeMission.progress.progress_percentage}%</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-cyan-500 h-full transition-all duration-300 ease-out rounded-full"
              style={{ width: `${activeMission.progress.progress_percentage}%` }}
            />
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="grid grid-cols-2 gap-2 pt-1">
        <button
          type="button"
          onClick={handleCreateMission}
          disabled={isLoading || isRunning}
          className="bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold py-1.5 px-3 rounded flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
        >
          <Send className="w-3.5 h-3.5 text-cyan-400" />
          Create Mission
        </button>

        {!isRunning && !isPaused && (
          <button
            type="button"
            onClick={() => handleAction("start")}
            disabled={isLoading || !activeMission}
            className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold py-1.5 px-3 rounded flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 fill-white" />
            Start Mission
          </button>
        )}

        {isRunning && (
          <button
            type="button"
            onClick={() => handleAction("pause")}
            disabled={isLoading}
            className="bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold py-1.5 px-3 rounded flex items-center justify-center gap-1.5 transition-colors"
          >
            <Pause className="w-3.5 h-3.5 fill-white" />
            Pause
          </button>
        )}

        {isPaused && (
          <button
            type="button"
            onClick={() => handleAction("resume")}
            disabled={isLoading}
            className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold py-1.5 px-3 rounded flex items-center justify-center gap-1.5 transition-colors"
          >
            <Play className="w-3.5 h-3.5 fill-white" />
            Resume
          </button>
        )}

        {(isRunning || isPaused) && (
          <button
            type="button"
            onClick={() => handleAction("cancel")}
            disabled={isLoading}
            className="col-span-2 bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800/80 text-xs font-semibold py-1.5 px-3 rounded flex items-center justify-center gap-1.5 transition-colors"
          >
            <XCircle className="w-3.5 h-3.5" />
            Cancel Mission
          </button>
        )}
      </div>
    </div>
  );
}
