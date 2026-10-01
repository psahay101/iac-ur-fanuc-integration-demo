"""ROS transport: joint-name mapping, controller readiness and action lifecycle.

Both OEMs speak FollowJointTrajectory. A configured instance is the adapter for
each robot; duplicating this code into cosmetic OEM subclasses adds no behavior.
The official stacks select their own hardware plugin, here in mock mode.
"""

import asyncio
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import rclpy
from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from controller_manager_msgs.srv import ListControllers
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectoryPoint

STALE_SECONDS = 1.5


@dataclass
class ExecutionResult:
    status: str
    detail: str


class RobotAdapter(Protocol):
    def state(self) -> dict: ...
    async def execute(self, points: list[tuple[list[float], float]], stop: asyncio.Event,
                      feedback: Callable[[float], None]) -> ExecutionResult: ...


async def ros_result(future, timeout: float = 3.0):
    """Keep rclpy callbacks on their executor; never block the web event loop."""
    deadline = time.monotonic() + timeout
    while not future.done():
        if time.monotonic() >= deadline:
            raise TimeoutError("ROS controller did not respond in time")
        await asyncio.sleep(0.02)
    return future.result()


class Ros2ControlAdapter:
    def __init__(self, node: Node, config: dict):
        self.node, self.config = node, config
        self.names = config["joint_names"]
        self._lock = threading.Lock()
        self._positions: list[float] = []
        self._velocities: list[float] = []
        self._received = 0.0
        self._controller_checked = 0.0
        self._controller_active = False
        self._controller_request = None
        self._controller_sent = 0.0
        self._feedback_seconds = 0.0
        self._fault = None
        self.action = ActionClient(node, FollowJointTrajectory, config["adapter"]["action"])
        self.subscription = node.create_subscription(
            JointState, config["adapter"]["joint_states"], self._on_joints, qos_profile_sensor_data)
        namespace, self.controller_name, _ = config["adapter"]["action"].rsplit("/", 2)
        self.controllers = node.create_client(ListControllers, namespace + "/controller_manager/list_controllers")
        self.timer = node.create_timer(0.5, self._check_controller)

    def _on_joints(self, message: JointState):
        # ROS messages may include additional joints or a different order.
        index = {name: i for i, name in enumerate(message.name)}
        try:
            positions = [message.position[index[name]] for name in self.names]
            velocities = [message.velocity[index[name]] if len(message.velocity) > index[name] else 0.0
                          for name in self.names]
        except (KeyError, IndexError):
            return
        if not all(math.isfinite(v) for v in positions + velocities):
            return
        with self._lock:
            self._positions, self._velocities = positions, velocities
            self._received = time.monotonic()

    def _check_controller(self):
        if self._controller_request is not None and not self._controller_request.done():
            if time.monotonic() - self._controller_sent < 3.0:
                return
            self._controller_request.cancel()
        if not self.controllers.service_is_ready():
            return
        self._controller_request = self.controllers.call_async(ListControllers.Request())
        self._controller_sent = time.monotonic()
        self._controller_request.add_done_callback(self._on_controllers)

    def _on_controllers(self, future):
        try:
            controllers = future.result().controller
            active = any(c.name == self.controller_name and c.state == "active" for c in controllers)
        except Exception:
            active = False
        with self._lock:
            self._controller_active = active
            self._controller_checked = time.monotonic()

    def state(self) -> dict:
        current = time.monotonic()
        with self._lock:
            age = current - self._received if self._received else None
            controller_ready = self._controller_active and current - self._controller_checked < 2.5
            positions, velocities = list(self._positions), list(self._velocities)
        controller_ready = controller_ready and self.action.server_is_ready()
        connected = age is not None and age < STALE_SECONDS and controller_ready and not self._fault
        connected = bool(connected)
        return {
            "id": self.config["id"], "status": "fault" if self._fault else "ready" if connected else "offline",
            "connected": connected, "controller_ready": controller_ready,
            "joint_positions": positions, "joint_velocities": velocities,
            "state_age_ms": round(age * 1000, 1) if age is not None else None,
            "active_mission": None,
            "detail": self._fault or ("Live ROS joint feedback" if connected else "Waiting for fresh joints and an active controller"),
        }

    def _on_feedback(self, message):
        elapsed = message.feedback.desired.time_from_start
        with self._lock:
            self._feedback_seconds = elapsed.sec + elapsed.nanosec / 1e9

    async def execute(self, points, stop, feedback) -> ExecutionResult:
        if not self.state()["connected"]:
            return ExecutionResult("failed", "Robot feedback is stale or the controller is inactive")
        if stop.is_set():
            return ExecutionResult("canceled", "Canceled before trajectory dispatch")
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = list(self.names)
        for positions, elapsed in points:
            point = JointTrajectoryPoint()
            point.positions = [float(v) for v in positions]
            # Zero end velocities give smooth cubic interpolation at each waypoint.
            point.velocities = [0.0] * len(self.names)
            sec = int(elapsed)
            point.time_from_start = Duration(sec=sec, nanosec=int((elapsed - sec) * 1e9))
            goal.trajectory.points.append(point)
        goal.goal_time_tolerance = Duration(sec=2)
        with self._lock:
            self._feedback_seconds = 0.0
        goal_future = self.action.send_goal_async(goal, feedback_callback=self._on_feedback)
        try:
            handle = await ros_result(goal_future)
        except (Exception, asyncio.CancelledError):
            self._fault = "Trajectory acknowledgement unconfirmed. Restart the demo before issuing new motion."
            # An acknowledgement can arrive late. Do not orphan an accepted move.
            def cancel_late_goal(future):
                try:
                    late_handle = future.result()
                    if late_handle.accepted:
                        late_handle.cancel_goal_async()
                except Exception:
                    pass
            goal_future.add_done_callback(cancel_late_goal)
            raise
        if not handle.accepted:
            return ExecutionResult("failed", "ROS controller rejected the trajectory")
        result_future = None
        total = points[-1][1]
        deadline = time.monotonic() + total + 8.0
        canceled = False
        health_failure = None
        try:
            result_future = handle.get_result_async()
            while not result_future.done():
                if not self.state()["connected"]:
                    health_failure = "Lost fresh feedback or the active ROS controller during execution"
                if (stop.is_set() or health_failure) and not canceled:
                    response = await ros_result(handle.cancel_goal_async())
                    canceled = True
                    if not response.goals_canceling:
                        # It may have just finished: the result remains authoritative.
                        deadline = min(deadline, time.monotonic() + 3.0)
                if time.monotonic() > deadline:
                    raise TimeoutError("Timed out waiting for the ROS trajectory result")
                with self._lock:
                    elapsed = self._feedback_seconds
                feedback(max(0.0, min(0.99, elapsed / total)))
                await asyncio.sleep(0.04)
            result = result_future.result()
            if health_failure:
                return ExecutionResult("failed", health_failure + "; cancellation requested")
            if result.status == GoalStatus.STATUS_CANCELED:
                return ExecutionResult("canceled", "ROS controller confirmed trajectory cancellation")
            if result.status == GoalStatus.STATUS_SUCCEEDED and result.result.error_code == 0:
                return ExecutionResult("succeeded", "ROS controller confirmed the target was reached")
            return ExecutionResult("failed", result.result.error_string or f"ROS action ended with status {result.status}, code {result.result.error_code}")
        except (Exception, asyncio.CancelledError):
            self._fault = "Trajectory outcome unconfirmed. Restart the demo before issuing new motion."
            raise
        finally:
            if result_future is None or not result_future.done():
                # Best effort on timeout/shutdown. No claim of a physical safety stop.
                try:
                    await ros_result(handle.cancel_goal_async(), timeout=1.0)
                except Exception:
                    pass


class RosBridge:
    """One ROS executor services all configured adapters beside the ASGI loop."""
    def __init__(self, configs: dict[str, dict]):
        self.context = Context()
        rclpy.init(args=[], context=self.context)
        self.node = Node("iac_platform_bridge", context=self.context)
        self.adapters = {key: Ros2ControlAdapter(self.node, cfg) for key, cfg in configs.items()}
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, name="ros-feedback", daemon=True)
        self.thread.start()

    def close(self):
        self.executor.shutdown(timeout_sec=2.0)
        self.thread.join(timeout=3.0)
        self.node.destroy_node()
        self.context.shutdown()
