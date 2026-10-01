/** The browser consumes the platform contract; OEM details arrive as metadata. */
export type Robot = {
  id: string;
  name: string;
  manufacturer: string;
  model: string;
  description: string;
  accent: string;
  dof: number;
  mode: string;
  urdf_url: string;
  tool_link: string;
  source_url: string;
  joint_names: string[];
  limits: { lower: number; upper: number; velocity: number }[];
  poses: { id: string; label: string }[];
  capabilities: string[];
  adapter: { name: string; action: string; joint_states: string };
};
export type RobotState = {
  id: string;
  status: "offline" | "ready" | "moving" | "stopping" | "fault";
  connected: boolean;
  joint_positions: number[];
  joint_velocities: number[];
  state_age_ms: number | null;
  active_mission: string | null;
  controller_ready: boolean;
  detail: string;
};
export type Mission = {
  id: string;
  type: string;
  robot: string;
  actor: string;
  inputs: Record<string, unknown>;
  status: "accepted" | "running" | "succeeded" | "canceled" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: number;
  phase: string;
  detail: string;
};
export type PlatformEvent = {
  id: number;
  timestamp: string;
  robot: string | null;
  mission: string | null;
  level: "info" | "success" | "warning" | "error";
  source: string;
  message: string;
};
export type Snapshot = {
  timestamp: string;
  mode: string;
  robots: RobotState[];
  missions: Mission[];
  events: PlatformEvent[];
};
export type MissionRequest = {
  id: string;
  type: string;
  robot: string;
  actor: string;
  inputs: Record<string, unknown>;
};
