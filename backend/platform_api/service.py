"""Local mission execution: validate, reserve one arm, dispatch, record outcome.

This is an in-memory demo mission manager, not a fleet scheduler or recovery DB.
The same code and commands run for every configured RobotAdapter.
"""

import asyncio
import math
from collections import deque
from typing import TYPE_CHECKING

from .domain import Mission, MissionRequest, PlatformError, now

if TYPE_CHECKING:
    from .ros_adapter import RobotAdapter


def number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise PlatformError(422, f"{label} must be a finite number")
    return float(value)


def plan(request: MissionRequest, config: dict, current: list[float]) -> list[tuple[list[float], float]]:
    """Resolve semantic poses to a small joint trajectory; no collision planner."""
    inputs = request.inputs
    allowed = {"move_named": {"pose", "duration"}, "move_joints": {"positions", "duration"}, "run_demo": {"duration"}}
    if set(inputs) - allowed[request.type]:
        raise PlatformError(422, f"Unknown inputs for {request.type}: {', '.join(sorted(set(inputs) - allowed[request.type]))}")
    duration = number(inputs.get("duration", 4.0), "duration")
    if not 2.0 <= duration <= 12.0:
        raise PlatformError(422, "duration must be between 2 and 12 seconds per segment")
    if request.type == "move_named":
        pose = inputs.get("pose")
        if not isinstance(pose, str) or pose not in config["pose_positions"]:
            raise PlatformError(422, "Unknown pose; choose a pose from the robot catalog")
        targets = [config["pose_positions"][pose]]
    elif request.type == "move_joints":
        targets = [inputs.get("positions")]
    else:
        targets = [config["pose_positions"][pose] for pose in config["demo_sequence"]]
    count = len(config["joint_names"])
    points = []
    previous = current
    for segment, target in enumerate(targets, 1):
        if not isinstance(target, list) or len(target) != count:
            raise PlatformError(422, f"positions must contain exactly {count} joint angles in radians")
        target = [number(v, f"joint {i + 1}") for i, v in enumerate(target)]
        for i, (angle, limit) in enumerate(zip(target, config["limits"])):
            if not limit["lower"] <= angle <= limit["upper"]:
                raise PlatformError(422, f"Joint {i + 1} is outside the configured position limits")
            # Zero end velocity cubic interpolation peaks at 1.5 * displacement / time.
            if len(previous) == count and 1.5 * abs(angle - previous[i]) / duration > limit["velocity"]:
                raise PlatformError(422, f"Joint {i + 1} would exceed its velocity limit; increase duration or reduce the move")
        points.append((target, segment * duration))
        previous = target
    return points


class MissionManager:
    def __init__(self, configs: dict, adapters: dict[str, "RobotAdapter"]):
        self.configs, self.adapters = configs, adapters
        self.missions: dict[str, Mission] = {}
        self.requests: dict[str, dict] = {}
        self.active: dict[str, str] = {}
        self.stops: dict[str, asyncio.Event] = {}
        self.tasks: set[asyncio.Task] = set()
        self.events: deque = deque(maxlen=100)
        self.event_id = 0
        self.connected: dict[str, bool] = {}
        self.event(None, None, "info", "platform", "Platform online · official ROS 2 stacks · mock hardware")

    def event(self, robot, mission, level, source, message):
        self.event_id += 1
        self.events.append({"id": self.event_id, "timestamp": now(), "robot": robot,
                            "mission": mission, "level": level, "source": source, "message": message})

    def submit(self, request: MissionRequest) -> Mission:
        config = self.configs.get(request.robot)
        if config is None:
            raise PlatformError(404, "Unknown robot")
        payload = request.model_dump()
        if request.id in self.requests:
            if self.requests[request.id] != payload:
                raise PlatformError(409, "This mission id already belongs to a different request")
            return self.missions[request.id]
        state = self.adapters[request.robot].state()
        # Validate even when offline, so malformed requests never reach execution.
        points = plan(request, config, state["joint_positions"])
        if request.robot in self.active:
            raise PlatformError(409, "Robot already has an active mission; cancel it or wait for completion")
        if not state["connected"]:
            raise PlatformError(503, "Robot unavailable: fresh joint feedback and an active ROS controller are required")
        mission = Mission(**payload)
        self.missions[request.id], self.requests[request.id] = mission, payload
        self.active[request.robot] = request.id
        stop = self.stops[request.robot] = asyncio.Event()
        self.event(request.robot, request.id, "info", "platform", f"Accepted {request.type} from {request.actor}")
        task = asyncio.create_task(self._run(mission, points, stop))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        # History and idempotency are bounded and intentionally process-local.
        completed = [key for key, m in self.missions.items() if m.finished_at]
        for key in completed[:-100]:
            self.missions.pop(key)
            self.requests.pop(key)
        return mission

    async def _run(self, mission, points, stop):
        mission.status, mission.started_at = "running", now()
        mission.phase = "Sending trajectory"
        self.event(mission.robot, mission.id, "info", "adapter", "Joint trajectory sent through the common adapter")

        def feedback(progress):
            mission.progress = progress
            segment = min(len(points), int(progress * len(points)) + 1)
            mission.phase = f"Waypoint {segment} of {len(points)}"

        try:
            result = await self.adapters[mission.robot].execute(points, stop, feedback)
            mission.status, mission.detail = result.status, result.detail
            if result.status == "succeeded":
                mission.progress = 1.0
            mission.phase = {"succeeded": "Completed", "canceled": "Canceled", "failed": "Failed"}[mission.status]
        except asyncio.CancelledError:
            mission.status, mission.phase = "failed", "Interrupted"
            mission.detail = "Platform shutdown interrupted execution; final controller outcome unconfirmed"
            raise
        except Exception as error:
            mission.status, mission.phase = "failed", "Failed"
            mission.detail = f"Adapter error: {error}"
        finally:
            mission.finished_at = now()
            self.active.pop(mission.robot, None)
            self.stops.pop(mission.robot, None)
            level = {"succeeded": "success", "canceled": "warning"}.get(mission.status, "error")
            self.event(mission.robot, mission.id, level, "controller", mission.detail)

    def stop(self, robot: str) -> dict:
        if robot not in self.configs:
            raise PlatformError(404, "Unknown robot")
        # No health gate: best-effort cancellation must remain available offline.
        signal = self.stops.get(robot)
        if signal is None:
            return {"accepted": False, "detail": "No platform trajectory is active"}
        signal.set()
        self.event(robot, self.active[robot], "warning", "platform", "Software cancellation requested")
        return {"accepted": True, "detail": "Cancellation requested; awaiting the controller result"}

    def snapshot(self) -> dict:
        states = []
        for robot, adapter in self.adapters.items():
            state = adapter.state()
            connected = state["connected"]
            if self.connected.get(robot) != connected:
                self.connected[robot] = connected
                self.event(robot, None, "success" if connected else "warning", "adapter",
                           "ROS feedback and controller ready" if connected else "ROS feedback or controller unavailable")
            active = self.active.get(robot)
            if active:
                state["active_mission"] = active
                state["status"] = "stopping" if self.stops[robot].is_set() else "moving" if connected else "fault"
            states.append(state)
        return {"timestamp": now(), "mode": "mock_hardware", "robots": states,
                "missions": [m.model_dump() for m in list(self.missions.values())[-30:]],
                "events": list(self.events)}

    async def close(self):
        for stop in self.stops.values():
            stop.set()
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=5.0)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
