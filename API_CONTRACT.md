# Platform API contract (v1)

All joint positions and limits are radians, times seconds. The UI renders catalog metadata and never branches on manufacturer, robot ID or joint names. Browser movement always comes from ROS joint states.

- `GET /api/robots` → `{robots: Robot[]}`
- `GET /api/state` → State
- `WS /api/events` → `{type: "snapshot", ...State}` at 10 Hz
- `POST /api/missions` → Mission (202); request `{id: string, type: "move_named" | "move_joints" | "run_demo", robot: string, actor: string, inputs: object}`
  - move_named inputs: `{pose: "ready" | "inspect" | "park", duration: 4}`
  - move_joints inputs: `{positions: number[], duration: 4}`
  - run_demo inputs: `{duration: 4}` (seconds per segment, sequence defined by robot config)
- `POST /api/robots/{id}/stop` → `{accepted: boolean, detail: string}`. Cancels the active trajectory. Software cancel, not a safety stop.
- API errors: `{detail: string}` (or a validation-issue array for malformed envelopes) with 404/409/422/503 status.
- `GET /api/health` → `{status, mode, ros_connected}`
- `GET /assets/{path}` static official generated URDF, referenced meshes and licenses. URDF mesh URLs rewritten to `/assets/...`.

Robot = `{id, name, manufacturer, model, description, accent, dof: 6, mode: "mock_hardware", urdf_url, tool_link, source_url, joint_names: string[], limits: [{lower, upper, velocity}], poses: [{id, label}], capabilities: ["move_named", "move_joints", "run_demo", "stop"], adapter: {name, action, joint_states}}`

State = `{timestamp: ISO8601, mode: "mock_hardware", robots: RobotState[], missions: Mission[], events: Event[]}`

Duration is 2–12 seconds per segment. `run_demo` runs Inspect → Park → Ready. Named poses resolve per robot; they are illustrative joint configurations, not equivalent calibrated Cartesian locations. Duplicate mission IDs with identical requests return the existing result while retained; changed payloads conflict. Deduplication/history are bounded and process-local.

RobotState = `{id, status: "offline" | "ready" | "moving" | "stopping" | "fault", connected: boolean, joint_positions: number[], joint_velocities: number[], state_age_ms: number|null, active_mission: string|null, controller_ready: boolean, detail: string}`

Mission = `{id, type, robot, actor, inputs, status: "accepted" | "running" | "succeeded" | "canceled" | "failed", created_at, started_at: string|null, finished_at: string|null, progress: number (0..1), phase: string, detail: string}`

Event = `{id: number, timestamp: ISO8601, robot: string|null, mission: string|null, level: "info"|"success"|"warning"|"error", source: "platform"|"adapter"|"controller", message: string}`

GET robots is catalog/config only; state tells connectivity. No optimistic fake progress or model animation in the browser. A stale socket/state must clearly disable motion. Backend handles busy/invalid/stale inputs. Normalized controller feedback determines progress; ROS action results determine success.
