"""Contract tests use test doubles only here. The demo never substitutes a fake API."""

import asyncio
import copy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.config import load_configs, validate_config
from platform_api.domain import MissionRequest, PlatformError
from platform_api.service import MissionManager, plan


class TestAdapter:
    __test__ = False

    def __init__(self, config):
        self.config = config
        self.connected = True
        self.calls = []
        self.outcome = "succeeded"
        self.hold = False

    def state(self):
        return {"id": self.config["id"], "status": "ready", "connected": self.connected,
                "controller_ready": self.connected, "joint_positions": self.config["pose_positions"]["ready"],
                "joint_velocities": [0.0] * 6, "active_mission": None,
                "state_age_ms": 10.0, "detail": "Test adapter"}

    async def execute(self, points, stop, feedback):
        self.calls.append(points)
        feedback(0.5)
        while self.hold and not stop.is_set():
            await asyncio.sleep(0.01)
        if self.outcome == "exception":
            raise RuntimeError("lost transport")
        return SimpleNamespace(status="canceled" if stop.is_set() else self.outcome, detail="Test controller result")


@pytest.fixture
def manager():
    configs = load_configs()
    return MissionManager(configs, {key: TestAdapter(c) for key, c in configs.items()})


def request(robot, **overrides):
    return MissionRequest(id="test-1", type="move_named", robot=robot, actor="test",
                          inputs={"pose": "inspect", "duration": 4}, **overrides)


@pytest.mark.parametrize("robot", ["ur", "fanuc"])
def test_same_contract_and_controller_result_for_both_robots(manager, robot):
    async def run():
        mission = manager.submit(request(robot))
        assert mission.status == "accepted"
        await asyncio.gather(*manager.tasks)
        assert mission.status == "succeeded"
        assert mission.progress == 1
        assert mission.actor == "test"
        assert manager.adapters[robot].calls[0][0][0] == manager.configs[robot]["pose_positions"]["inspect"]
        assert robot not in manager.active
    asyncio.run(run())


@pytest.mark.parametrize("inputs", [
    {"pose": "unknown"}, {"pose": "ready", "weld_ticks": 3}, {"pose": "ready", "duration": True},
    {"pose": "ready", "duration": float("nan")}, {"pose": "ready", "duration": 0.1},
    {"pose": ["ready"]},
])
def test_invalid_inputs_never_dispatch(manager, inputs):
    req = request("ur")
    req.inputs = inputs
    with pytest.raises(PlatformError) as error:
        manager.submit(req)
    assert error.value.status == 422
    assert not manager.adapters["ur"].calls
    assert not manager.missions


@pytest.mark.parametrize("positions", [[0], [False] * 6, [float("inf")] * 6, [1000] * 6])
def test_invalid_joint_targets_rejected(manager, positions):
    req = MissionRequest(id="joints", type="move_joints", robot="ur", actor="test", inputs={"positions": positions})
    with pytest.raises(PlatformError):
        manager.submit(req)


def test_velocity_limit_checked_against_start_and_each_waypoint(manager):
    config = copy.deepcopy(manager.configs["ur"])
    config["limits"][0]["velocity"] = 0.01
    with pytest.raises(PlatformError, match="velocity"):
        plan(request("ur"), config, config["initial_positions"])


def test_busy_idempotency_and_cancel_when_unhealthy(manager):
    async def run():
        adapter = manager.adapters["ur"]
        adapter.hold = True
        req = request("ur")
        first = manager.submit(req)
        assert manager.submit(req) is first
        changed = req.model_copy(update={"actor": "someone-else"})
        with pytest.raises(PlatformError, match="different request"):
            manager.submit(changed)
        second = req.model_copy(update={"id": "test-2"})
        with pytest.raises(PlatformError, match="active mission"):
            manager.submit(second)
        await asyncio.sleep(0.02)
        adapter.connected = False
        assert manager.stop("ur")["accepted"] is True
        await asyncio.gather(*manager.tasks)
        assert first.status == "canceled"
        assert len(adapter.calls) == 1
        assert manager.stop("ur")["accepted"] is False
    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["failed", "exception"])
def test_failures_recorded_and_reservation_released(manager, outcome):
    async def run():
        manager.adapters["ur"].outcome = outcome
        mission = manager.submit(request("ur"))
        await asyncio.gather(*manager.tasks)
        assert mission.status == "failed"
        assert mission.finished_at
        assert "ur" not in manager.active
    asyncio.run(run())


def test_missing_feedback_blocks_work(manager):
    manager.adapters["ur"].connected = False
    with pytest.raises(PlatformError) as error:
        manager.submit(request("ur"))
    assert error.value.status == 503
    assert not manager.missions


@pytest.mark.parametrize("fault", ["missing_limit", "duplicate_joint", "missing_pose"])
def test_bad_model_configuration_fails_before_startup(manager, fault):
    config = copy.deepcopy(manager.configs["ur"])
    if fault == "missing_limit":
        config["limits"].pop()
    elif fault == "duplicate_joint":
        config["joint_names"][1] = config["joint_names"][0]
    else:
        config["demo_sequence"].append("unknown")
    with pytest.raises(ValueError):
        validate_config(config)


def test_http_envelope_catalog_and_websocket(manager):
    with TestClient(create_app(manager)) as client:
        catalog = client.get("/api/robots").json()["robots"]
        assert {r["id"] for r in catalog} == {"ur", "fanuc"}
        assert catalog[0]["capabilities"] == catalog[1]["capabilities"]
        assert all("pose_positions" not in r for r in catalog)
        bad = client.post("/api/missions", json={"mission_id": "old", "task": "weld"})
        assert bad.status_code == 422
        payload = request("ur").model_dump()
        payload["robot"] = "unknown"
        assert client.post("/api/missions", json=payload).status_code == 404
        assert client.post("/api/robots/unknown/stop").status_code == 404
        with client.websocket_connect("/api/events") as socket:
            state = socket.receive_json()
            assert state["type"] == "snapshot"
            assert state["mode"] == "mock_hardware"
        result = client.post("/api/missions", json=request("ur").model_dump())
        assert result.status_code == 202
        assert result.json()["actor"] == "test"
