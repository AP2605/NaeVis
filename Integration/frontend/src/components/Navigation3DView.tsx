"use client";

import React, { useRef, useMemo, useState, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid, Html, Line } from "@react-three/drei";
import * as THREE from "three";
import {
  Compass,
  Eye,
  Layers,
  Maximize2,
  Navigation,
  RotateCcw,
  Sliders,
} from "lucide-react";
import {
  Mission,
  Position3D,
  SimulationGroundTruthPacket,
  Telemetry,
  TrajectoryPoint,
} from "../types/telemetry";

/**
 * Explicit Coordinate System Transformation Layer:
 * Blender Simulation frame: X (Forward), Y (Right/Lateral), Z (Altitude Up)
 * Three.js World frame: X (Right), Y (Up), Z (Forward/Depth)
 * Transformation: [x_three = x_sim, y_three = z_sim, z_three = -y_sim]
 */
export function simToThree(x: number, y: number, z: number): [number, number, number] {
  return [x, z, -y];
}

interface DroneMeshProps {
  position: [number, number, number];
  orientation: { roll: number; pitch: number; yaw: number };
  color?: string;
  isGhost?: boolean;
}

function DroneModel({ position, orientation, color = "#06b6d4", isGhost = false }: DroneMeshProps) {
  const groupRef = useRef<THREE.Group>(null);
  const rotorRef1 = useRef<THREE.Mesh>(null);
  const rotorRef2 = useRef<THREE.Mesh>(null);
  const rotorRef3 = useRef<THREE.Mesh>(null);
  const rotorRef4 = useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.position.set(position[0], position[1], position[2]);
      // Degrees to Radians conversion at render boundary
      const rollRad = (orientation.roll * Math.PI) / 180;
      const pitchRad = (orientation.pitch * Math.PI) / 180;
      const yawRad = (orientation.yaw * Math.PI) / 180;
      groupRef.current.rotation.set(pitchRad, yawRad, -rollRad, "YXZ");
    }

    // Spin rotors
    const spinSpeed = 25.0 * delta;
    if (rotorRef1.current) rotorRef1.current.rotation.y += spinSpeed;
    if (rotorRef2.current) rotorRef2.current.rotation.y -= spinSpeed;
    if (rotorRef3.current) rotorRef3.current.rotation.y += spinSpeed;
    if (rotorRef4.current) rotorRef4.current.rotation.y -= spinSpeed;
  });

  return (
    <group ref={groupRef}>
      {/* Central Chassis */}
      <mesh castShadow>
        <boxGeometry args={[0.9, 0.25, 0.9]} />
        <meshStandardMaterial
          color={isGhost ? "#10b981" : "#1e293b"}
          metalness={0.8}
          roughness={0.2}
          transparent={isGhost}
          opacity={isGhost ? 0.4 : 1.0}
        />
      </mesh>

      {/* Top Dome / Flight Controller Cover */}
      <mesh position={[0, 0.2, 0]}>
        <cylinderGeometry args={[0.3, 0.35, 0.2, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} />
      </mesh>

      {/* Heading Indicator Cone (Nose Pointer) */}
      <mesh position={[0, 0.05, 0.7]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.18, 0.45, 12]} />
        <meshStandardMaterial color="#38bdf8" emissive="#38bdf8" emissiveIntensity={0.8} />
      </mesh>

      {/* 4 Carbon Arms (X-Configuration) */}
      <mesh rotation={[0, Math.PI / 4, 0]}>
        <boxGeometry args={[2.2, 0.08, 0.12]} />
        <meshStandardMaterial color="#334155" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh rotation={[0, -Math.PI / 4, 0]}>
        <boxGeometry args={[2.2, 0.08, 0.12]} />
        <meshStandardMaterial color="#334155" metalness={0.9} roughness={0.1} />
      </mesh>

      {/* 4 Motor Pods & Rotors */}
      {[
        [-0.78, 0.1, 0.78, rotorRef1],
        [0.78, 0.1, 0.78, rotorRef2],
        [-0.78, 0.1, -0.78, rotorRef3],
        [0.78, 0.1, -0.78, rotorRef4],
      ].map(([mx, my, mz, ref], idx) => (
        <group key={idx} position={[mx as number, my as number, mz as number]}>
          <mesh>
            <cylinderGeometry args={[0.16, 0.16, 0.18, 12]} />
            <meshStandardMaterial color="#0f172a" />
          </mesh>
          {/* Propeller Blade */}
          <mesh ref={ref as any} position={[0, 0.12, 0]}>
            <boxGeometry args={[0.9, 0.02, 0.1]} />
            <meshStandardMaterial
              color={color}
              transparent
              opacity={0.7}
              emissive={color}
              emissiveIntensity={0.4}
            />
          </mesh>
        </group>
      ))}

      {/* Ground Projection Altitude Drop Line */}
      <Line
        points={[[0, 0, 0], [0, -position[1], 0]]}
        color={color}
        lineWidth={1}
        dashed
        dashSize={0.5}
        gapSize={0.3}
        opacity={0.3}
        transparent
      />
    </group>
  );
}

function TrajectoryLine({
  points,
  color,
  dashed = false,
}: {
  points: [number, number, number][];
  color: string;
  dashed?: boolean;
}) {
  if (points.length < 2) return null;

  return (
    <Line
      points={points}
      color={color}
      lineWidth={2}
      dashed={dashed}
      dashSize={dashed ? 0.8 : undefined}
      gapSize={dashed ? 0.4 : undefined}
      transparent
      opacity={0.85}
    />
  );
}

interface WaypointMarkersProps {
  mission: Mission | null;
  simDronePos: { x: number; y: number; z: number };
  trajectoryHistory?: { ground_truth: TrajectoryPoint[]; estimated: TrajectoryPoint[] } | null;
}

function WaypointMarkers({ mission, simDronePos, trajectoryHistory }: WaypointMarkersProps) {
  if (!mission) return null;

  const srcPos = simToThree(mission.source.x, mission.source.y, mission.source.z);
  const destPos = simToThree(mission.destination.x, mission.destination.y, mission.destination.z);

  const SPATIAL_THRESHOLD = 3.5; // Spatial threshold (meters) for reaching a waypoint

  // Derive status (REACHED, CURRENT, PENDING) for each waypoint dynamically
  const waypointStatuses = useMemo(() => {
    if (!mission.waypoints || mission.waypoints.length === 0) return [];

    const isMissionCompleted = mission.status === "COMPLETED";
    const estPoints = trajectoryHistory?.estimated ?? [];

    let highestReachedIndex = -1;

    if (isMissionCompleted) {
      highestReachedIndex = mission.waypoints.length - 1;
    } else {
      for (let i = 0; i < mission.waypoints.length; i++) {
        const wp = mission.waypoints[i];

        // 1. Explicit backend waypoint status
        if (wp.status === "REACHED") {
          highestReachedIndex = Math.max(highestReachedIndex, i);
          continue;
        }

        // 2. Live estimated drone proximity
        const distCurrent = Math.hypot(
          simDronePos.x - wp.x,
          simDronePos.y - wp.y,
          simDronePos.z - wp.z
        );
        if (distCurrent <= SPATIAL_THRESHOLD) {
          highestReachedIndex = Math.max(highestReachedIndex, i);
          continue;
        }

        // 3. Proximity check across recent trajectory trail
        const reachedInTrail = estPoints.some((p) => {
          return Math.hypot(p.x - wp.x, p.y - wp.y, p.z - wp.z) <= SPATIAL_THRESHOLD;
        });
        if (reachedInTrail) {
          highestReachedIndex = Math.max(highestReachedIndex, i);
        }
      }

      // 4. Backend progress telemetry
      if (mission.progress?.waypoints_completed) {
        highestReachedIndex = Math.max(
          highestReachedIndex,
          mission.progress.waypoints_completed - 1
        );
      }
    }

    return mission.waypoints.map((_, idx) => {
      if (idx <= highestReachedIndex) return "REACHED";
      if (idx === highestReachedIndex + 1) return "CURRENT";
      return "PENDING";
    });
  }, [
    mission.status,
    mission.waypoints,
    mission.progress?.waypoints_completed,
    simDronePos.x,
    simDronePos.y,
    simDronePos.z,
    trajectoryHistory?.estimated,
  ]);

  // Destination reached status
  const isDestReached = useMemo(() => {
    if (mission.status === "COMPLETED") return true;
    const distToDest = Math.hypot(
      simDronePos.x - mission.destination.x,
      simDronePos.y - mission.destination.y,
      simDronePos.z - mission.destination.z
    );
    if (distToDest <= SPATIAL_THRESHOLD) return true;
    const estPoints = trajectoryHistory?.estimated ?? [];
    return estPoints.some(
      (p) =>
        Math.hypot(
          p.x - mission.destination.x,
          p.y - mission.destination.y,
          p.z - mission.destination.z
        ) <= SPATIAL_THRESHOLD
    );
  }, [
    mission.status,
    mission.destination.x,
    mission.destination.y,
    mission.destination.z,
    simDronePos.x,
    simDronePos.y,
    simDronePos.z,
    trajectoryHistory?.estimated,
  ]);

  return (
    <group>
      {/* Source Marker */}
      <group position={srcPos}>
        <mesh>
          <sphereGeometry args={[0.6, 16, 16]} />
          <meshStandardMaterial color="#10b981" emissive="#10b981" emissiveIntensity={0.8} />
        </mesh>
        <Html distanceFactor={25} position={[0, 1.2, 0]} center>
          <div className="bg-emerald-950/90 text-emerald-400 border border-emerald-500/40 text-[10px] px-1.5 py-0.5 rounded font-mono font-bold whitespace-nowrap shadow-lg">
            SRC ({mission.source.x.toFixed(0)},{mission.source.y.toFixed(0)})
          </div>
        </Html>
      </group>

      {/* Destination Marker */}
      <group position={destPos}>
        <mesh>
          <cylinderGeometry args={[0.7, 0.7, 0.4, 16]} />
          <meshStandardMaterial
            color={isDestReached ? "#10b981" : "#f59e0b"}
            emissive={isDestReached ? "#10b981" : "#f59e0b"}
            emissiveIntensity={isDestReached ? 0.8 : 0.9}
          />
        </mesh>
        <Html distanceFactor={25} position={[0, 1.2, 0]} center>
          <div
            className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-bold whitespace-nowrap border shadow-lg ${
              isDestReached
                ? "bg-emerald-950/90 text-emerald-400 border-emerald-500/40"
                : "bg-amber-950/90 text-amber-400 border-amber-500/40"
            }`}
          >
            DEST ({mission.destination.x.toFixed(0)},{mission.destination.y.toFixed(0)})
          </div>
        </Html>
      </group>

      {/* Intermediate Waypoints */}
      {mission.waypoints.map((wp, idx) => {
        const wpPos = simToThree(wp.x, wp.y, wp.z);
        const status = waypointStatuses[idx] || "PENDING";
        const isReached = status === "REACHED";
        const isCurrent = status === "CURRENT";
        const wpColor = isReached ? "#10b981" : isCurrent ? "#f59e0b" : "#64748b";

        return (
          <group key={idx} position={wpPos}>
            <mesh>
              <sphereGeometry args={[0.5, 16, 16]} />
              <meshStandardMaterial
                color={wpColor}
                emissive={wpColor}
                emissiveIntensity={isCurrent ? 0.9 : isReached ? 0.6 : 0.2}
              />
            </mesh>
            <Html distanceFactor={25} position={[0, 1.0, 0]} center>
              <div
                className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold whitespace-nowrap border shadow-md ${
                  isReached
                    ? "bg-emerald-950/90 text-emerald-300 border-emerald-500/40"
                    : isCurrent
                    ? "bg-amber-950/90 text-amber-300 border-amber-500/40 animate-pulse"
                    : "bg-slate-900/90 text-slate-400 border-slate-700"
                }`}
              >
                WP {idx + 1}
              </div>
            </Html>
          </group>
        );
      })}
    </group>
  );
}

function CameraController({
  targetPos,
  follow,
  controlsRef,
}: {
  targetPos: [number, number, number];
  follow: boolean;
  controlsRef: React.RefObject<any>;
}) {
  useFrame(() => {
    if (follow && controlsRef.current) {
      controlsRef.current.target.lerp(
        new THREE.Vector3(targetPos[0], targetPos[1], targetPos[2]),
        0.08
      );
      controlsRef.current.update();
    }
  });
  return null;
}

interface Navigation3DViewProps {
  telemetry: Telemetry | null;
  groundTruth: SimulationGroundTruthPacket | null;
  mission: Mission | null;
  trajectoryHistory?: { ground_truth: TrajectoryPoint[]; estimated: TrajectoryPoint[] } | null;
}

export function Navigation3DView({
  telemetry,
  groundTruth,
  mission,
  trajectoryHistory,
}: Navigation3DViewProps) {
  const [showGroundTruth, setShowGroundTruth] = useState(true);
  const [showEstTraj, setShowEstTraj] = useState(true);
  const [showWaypoints, setShowWaypoints] = useState(true);
  const [followDrone, setFollowDrone] = useState(false);
  const [cameraView, setCameraView] = useState<"iso" | "top">("iso");

  const controlsRef = useRef<any>(null);

  // Derive Current Drone Position & Orientation
  const estPos = telemetry ? simToThree(telemetry.x, telemetry.y, telemetry.z) : simToThree(0, 0, 10);
  const estAtt = telemetry
    ? { roll: telemetry.roll, pitch: telemetry.pitch, yaw: telemetry.yaw }
    : { roll: 0, pitch: 0, yaw: 0 };

  const gtPos = groundTruth ? simToThree(groundTruth.position.x, groundTruth.position.y, groundTruth.position.z) : null;
  const gtAtt = groundTruth
    ? {
        roll: groundTruth.orientation.roll,
        pitch: groundTruth.orientation.pitch,
        yaw: groundTruth.orientation.yaw,
      }
    : { roll: 0, pitch: 0, yaw: 0 };

  // Trajectory Lines Arrays (mapped to Three.js coordinates)
  const estTrajPoints = useMemo(() => {
    if (!trajectoryHistory?.estimated) return [];
    return trajectoryHistory.estimated.map((p) => simToThree(p.x, p.y, p.z));
  }, [trajectoryHistory?.estimated]);

  const gtTrajPoints = useMemo(() => {
    if (!trajectoryHistory?.ground_truth) return [];
    return trajectoryHistory.ground_truth.map((p) => simToThree(p.x, p.y, p.z));
  }, [trajectoryHistory?.ground_truth]);

  // Handle View Reset / Preset Views
  const resetCamera = (mode: "iso" | "top") => {
    if (!controlsRef.current) return;
    setCameraView(mode);
    if (mode === "top") {
      controlsRef.current.object.position.set(estPos[0], estPos[1] + 60, estPos[2] + 0.1);
      controlsRef.current.target.set(estPos[0], 0, estPos[2]);
    } else {
      controlsRef.current.object.position.set(estPos[0] + 25, estPos[1] + 20, estPos[2] + 25);
      controlsRef.current.target.set(estPos[0], estPos[1], estPos[2]);
    }
    controlsRef.current.update();
  };

  // Sim Drone Coordinates for metric distance checks
  const simDronePos = useMemo(() => {
    if (telemetry) {
      return { x: telemetry.x, y: telemetry.y, z: telemetry.z };
    }
    return { x: 0, y: 0, z: 10 };
  }, [telemetry?.x, telemetry?.y, telemetry?.z]);

  return (
    <div className="relative w-full h-full min-h-[380px] bg-slate-950 rounded-lg overflow-hidden border border-slate-800 shadow-xl flex flex-col">
      {/* 3D Scene Header Bar */}
      <div className="absolute top-0 left-0 right-0 z-10 bg-slate-900/80 backdrop-blur-md px-3 py-2 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Navigation className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-semibold tracking-wider text-slate-200 uppercase">
            3D Navigation & Trajectory View
          </span>
          <span className="text-[10px] bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 px-1.5 py-0.5 rounded font-mono">
            BLENDER_LOCAL (1 unit ≈ 1m)
          </span>
        </div>

        {/* 3D Control Buttons */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setFollowDrone(!followDrone)}
            className={`px-2 py-1 text-[11px] rounded flex items-center gap-1 transition-colors ${
              followDrone
                ? "bg-cyan-600 text-white font-medium"
                : "bg-slate-800/80 text-slate-300 hover:bg-slate-700"
            }`}
            title="Lock camera target to drone position"
          >
            <Compass className="w-3 h-3" />
            Follow
          </button>
          <button
            onClick={() => resetCamera("top")}
            className={`px-2 py-1 text-[11px] rounded flex items-center gap-1 transition-colors ${
              cameraView === "top" ? "bg-slate-700 text-cyan-300" : "bg-slate-800/80 text-slate-300 hover:bg-slate-700"
            }`}
          >
            Top View
          </button>
          <button
            onClick={() => resetCamera("iso")}
            className="px-2 py-1 text-[11px] bg-slate-800/80 hover:bg-slate-700 text-slate-300 rounded flex items-center gap-1 transition-colors"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>
      </div>

      {/* WebGL Canvas */}
      <div className="w-full h-full flex-1">
        <Canvas
          camera={{ position: [25, 20, 25], fov: 50, near: 0.1, far: 1000 }}
          shadows
        >
          <ambientLight intensity={0.65} />
          <directionalLight position={[30, 50, 30]} intensity={1.2} castShadow />
          <pointLight position={[-20, 30, -20]} intensity={0.4} />

          {/* Coordinate Ground Plane Grid */}
          <Grid
            args={[150, 150]}
            cellSize={2}
            cellThickness={0.6}
            cellColor="#1e293b"
            sectionSize={10}
            sectionThickness={1.2}
            sectionColor="#334155"
            fadeDistance={120}
            fadeStrength={1.5}
            position={[0, 0, 0]}
          />

          {/* Axes Helper (Red=X Forward, Green=Y Up, Blue=Z Right) */}
          <primitive object={new THREE.AxesHelper(5)} position={[0, 0.05, 0]} />

          {/* Estimated Drone Model (Primary) */}
          <DroneModel position={estPos} orientation={estAtt} color="#06b6d4" />

          {/* Ground Truth Drone Ghost Model */}
          {showGroundTruth && gtPos && (
            <DroneModel position={gtPos} orientation={gtAtt} color="#10b981" isGhost />
          )}

          {/* Waypoints & Target Markers */}
          {showWaypoints && (
            <WaypointMarkers
              mission={mission}
              simDronePos={simDronePos}
              trajectoryHistory={trajectoryHistory}
            />
          )}

          {/* Estimated Trajectory Path */}
          {showEstTraj && <TrajectoryLine points={estTrajPoints} color="#06b6d4" />}

          {/* Reference / Ground Truth Trajectory Path */}
          {showGroundTruth && <TrajectoryLine points={gtTrajPoints} color="#10b981" />}

          {/* Camera Follow Controller */}
          <CameraController targetPos={estPos} follow={followDrone} controlsRef={controlsRef} />

          <OrbitControls
            ref={controlsRef}
            enableDamping
            dampingFactor={0.08}
            minDistance={3}
            maxDistance={250}
            maxPolarAngle={Math.PI / 2 + 0.05} // Don't flip below ground
          />
        </Canvas>
      </div>

      {/* 3D Legend & Visibility Toggles Bar */}
      <div className="absolute bottom-2 left-2 right-2 z-10 bg-slate-900/90 backdrop-blur-md p-2 rounded-md border border-slate-800 flex flex-wrap items-center justify-between text-[11px] gap-2">
        {/* Legend */}
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-sm shadow-cyan-500/50 inline-block" />
            Estimated Drone
          </span>
          <span className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-500/50 inline-block" />
            Ground Truth
          </span>
          <span className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded bg-amber-400 inline-block" />
            Waypoint / Target
          </span>
        </div>

        {/* Visibility Toggles */}
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 cursor-pointer text-slate-400 hover:text-slate-200">
            <input
              type="checkbox"
              checked={showGroundTruth}
              onChange={(e) => setShowGroundTruth(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-emerald-500 focus:ring-0"
            />
            Ground Truth
          </label>
          <label className="flex items-center gap-1 cursor-pointer text-slate-400 hover:text-slate-200">
            <input
              type="checkbox"
              checked={showEstTraj}
              onChange={(e) => setShowEstTraj(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-0"
            />
            Est. Trajectory
          </label>
          <label className="flex items-center gap-1 cursor-pointer text-slate-400 hover:text-slate-200">
            <input
              type="checkbox"
              checked={showWaypoints}
              onChange={(e) => setShowWaypoints(e.target.checked)}
              className="rounded bg-slate-800 border-slate-700 text-amber-500 focus:ring-0"
            />
            Waypoints
          </label>
        </div>
      </div>
    </div>
  );
}
