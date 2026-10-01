"""Adapter edge cases without DDS; end-to-end tests exercise the real controllers."""

import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sensor_msgs.msg import JointState

from platform_api.config import load_configs
from platform_api import ros_adapter


@pytest.fixture
def adapter(monkeypatch):
    action = Mock()
    action.server_is_ready.return_value = True
    monkeypatch.setattr(ros_adapter, "ActionClient", lambda *args: action)
    instance = ros_adapter.Ros2ControlAdapter(Mock(), load_configs()["ur"])
    return instance


def joint_message(adapter, *, reverse=False):
    names = list(adapter.names)
    positions = [0.1 * (i + 1) for i in range(len(names))]
    velocities = [0.01 * (i + 1) for i in range(len(names))]
    if reverse:
        names.reverse()
        positions.reverse()
        velocities.reverse()
    return JointState(name=["extra_joint"] + names, position=[0.0] + positions,
                      velocity=[0.0] + velocities)


def test_joint_feedback_is_reordered_and_extra_joints_ignored(adapter, monkeypatch):
    monkeypatch.setattr(ros_adapter.time, "monotonic", lambda: 100.0)
    adapter._on_joints(joint_message(adapter, reverse=True))
    state = adapter.state()
    assert state["joint_positions"] == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert state["joint_velocities"] == pytest.approx([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])


@pytest.mark.parametrize("bad_feedback", ["missing_joint", "short_positions", "nan", "infinite_velocity"])
def test_invalid_joint_feedback_never_refreshes_health(adapter, monkeypatch, bad_feedback):
    clock = [100.0]
    monkeypatch.setattr(ros_adapter.time, "monotonic", lambda: clock[0])
    adapter._controller_active = True
    adapter._controller_checked = 100.0
    adapter._on_joints(joint_message(adapter))
    original = adapter.state()["joint_positions"]
    assert adapter.state()["connected"]
    clock[0] = 101.6
    message = joint_message(adapter)
    if bad_feedback == "missing_joint":
        message.name[-1] = "unknown"
    elif bad_feedback == "short_positions":
        message.position = [0.0]
    elif bad_feedback == "nan":
        message.position[-1] = float("nan")
    else:
        message.velocity[-1] = float("inf")
    adapter._on_joints(message)
    state = adapter.state()
    assert state["joint_positions"] == original
    assert state["state_age_ms"] == 1600.0
    assert not state["connected"]


def test_fresh_joints_do_not_mask_stale_controller_status(adapter, monkeypatch):
    monkeypatch.setattr(ros_adapter.time, "monotonic", lambda: 103.0)
    adapter._controller_active = True
    adapter._controller_checked = 100.0
    adapter._on_joints(joint_message(adapter))
    state = adapter.state()
    assert state["state_age_ms"] == 0.0
    assert not state["controller_ready"]
    assert not state["connected"]


@pytest.mark.parametrize("interruption", [TimeoutError, asyncio.CancelledError])
def test_late_accepted_goal_is_canceled_after_ack_wait_is_interrupted(adapter, monkeypatch, interruption):
    adapter.state = lambda: {"connected": True}
    pending_ack = Future()
    adapter.action.send_goal_async.return_value = pending_ack

    async def interrupted_wait(*args, **kwargs):
        raise interruption()

    monkeypatch.setattr(ros_adapter, "ros_result", interrupted_wait)
    with pytest.raises(interruption):
        asyncio.run(adapter.execute([([0.0] * 6, 2.0)], asyncio.Event(), lambda _: None))
    late_handle = SimpleNamespace(accepted=True, cancel_goal_async=Mock())
    pending_ack.set_result(late_handle)
    late_handle.cancel_goal_async.assert_called_once()
