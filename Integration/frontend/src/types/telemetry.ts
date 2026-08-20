/**
 * SIH-NAVIS Integration Types
 */

export interface Position3D {
  x: number;
  y: number;
  z: number;
}

export interface Orientation3D {
  roll: number;
  pitch: number;
  yaw: number;
}

export interface Velocity3D {
  x: number;
  y: number;
  z: number;
}

export interface LidarData {
  front?: number;
  front_left?: number;
  front_right?: number;
  bottom?: number;
  left?: number;
  right?: number;
  back?: number;
}

export interface CameraReference {
  frame_id?: number;
  image_path?: string;
  timestamp?: number;
  width?: number;
  height?: number;
}

export interface SimulationGroundTruthPacket {
  timestamp: number;
  frame_id?: number;
  position: Position3D;
  orientation: Orientation3D;
  lidar?: LidarData;
  camera?: CameraReference;
}

export interface EstimatedPose {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
}

export interface NavigationStatePacket {
  frame_id: number;
  timestamp: number;
  estimated_pose: EstimatedPose;
  velocity: Velocity3D;
  tracking_state: string;
  confidence: number;
  processing_time_ms?: number;
}

export interface Landmark {
  landmark_id: string | number;
  label: string;
  confidence: number;
  bbox?: number[];
  estimated_relative_pos?: Position3D;
}

export interface TerrainResult {
  terrain_type: string;
  confidence: number;
  roughness?: number;
  features?: string[];
}

export interface SegmentationResult {
  classes: string[];
  mask_path?: string;
  coverage_percentages?: Record<string, number>;
}

export interface P1VisionResult {
  frame_id: number;
  timestamp: number;
  terrain: TerrainResult;
  segmentation: SegmentationResult;
  landmarks: Landmark[];
  place_recognition?: {
    match_found: boolean;
    location_id?: string;
    similarity_score?: number;
    reference_coordinates?: Position3D;
  };
  terrain_match?: {
    matched: boolean;
    elevation_estimate?: number;
    map_tile_id?: string;
    correlation_score?: number;
  };
  mission_awareness?: {
    threat_detected: boolean;
    landing_zone_viable: boolean;
    notes?: string;
  };
  visual_localization_hint?: {
    suggested_correction?: Position3D;
    uncertainty_radius?: number;
    hint_confidence?: number;
  };
  system?: {
    model_version?: string;
    inference_time_ms: number;
    device?: string;
    gpu_utilization_pct?: number;
  };
}

export interface IntegratedState {
  current_frame_id?: number;
  latest_timestamp?: number;
  ground_truth?: SimulationGroundTruthPacket;
  navigation?: NavigationStatePacket;
  perception?: P1VisionResult;
  latest_camera?: CameraReference;
  sync_status?: Record<string, any>;
  system_status?: Record<string, any>;
}

export interface Telemetry {
  x: number;
  y: number;
  z: number;
  velocity: number;
  roll: number;
  pitch: number;
  yaw: number;
  confidence: number;
  timestamp: string;
}

export interface WebSocketEvent<T = any> {
  event: string;
  timestamp: string;
  data: T;
}
