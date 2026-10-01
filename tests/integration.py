"""Exercise the real HTTP → ROS → controller → joint feedback path for each robot.

Run with the app running: .venv/bin/python tests/integration.py
Optional --controller-cycle needs a sourced Humble shell on the demo ROS domain.
This script never replaces the backend or generates simulated joint feedback.
"""

import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid

import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-cycle", action="store_true")
    args = parser.parse_args()
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=5)
    robots = client.get("/api/robots").json()["robots"]
    configs = {r["id"]: json.loads((ROOT / "config" / (r["id"] + ".json")).read_text()) for r in robots}
    assert len(robots) == 2, "Both OEM catalogs must be present"
    assert client.get("/api/health").json()["status"] == "ready"
    with connect("ws://127.0.0.1:8000/api/events", origin="http://localhost:8000") as socket:
        streamed = json.loads(socket.recv(timeout=3))
        assert streamed["type"] == "snapshot" and len(streamed["robots"]) == len(robots)
    summary = {"mode": "mock_hardware", "robots": {}, "checks": []}

    def state():
        response = client.get("/api/state")
        response.raise_for_status()
        return response.json()

    def submit(robot, kind="move_named", inputs=None):
        payload = {"id": "verify-" + uuid.uuid4().hex[:12], "type": kind, "robot": robot,
                   "actor": "integration-test", "inputs": inputs or {"pose": "inspect", "duration": 3.0}}
        response = client.post("/api/missions", json=payload)
        assert response.status_code == 202, response.text
        return payload

    def wait_all(requests, expected="succeeded", timeout=25):
        deadline = time.monotonic() + timeout
        observed = {r["robot"]: [] for r in requests}
        while time.monotonic() < deadline:
            snapshot = state()
            missions = {m["id"]: m for m in snapshot["missions"]}
            for robot in snapshot["robots"]:
                if robot["id"] in observed:
                    observed[robot["id"]].append(robot["joint_positions"])
            relevant = [missions[r["id"]] for r in requests]
            if all(m["finished_at"] for m in relevant):
                assert all(m["status"] == expected for m in relevant), relevant
                return observed
            time.sleep(0.08)
        raise AssertionError("Missions did not finish within the test deadline")

    # Establish the same starting pose even after someone has used the web UI.
    wait_all([submit(r["id"], inputs={"pose": "ready", "duration": 3.0}) for r in robots])
    starts = {r["id"]: r["joint_positions"] for r in state()["robots"]}
    requests = [submit(r["id"]) for r in robots]
    # Retry is idempotent, and a competing command cannot preempt an active mission.
    for request in requests:
        assert client.post("/api/missions", json=request).status_code == 202
        competing = dict(request, id="busy-" + request["id"])
        assert client.post("/api/missions", json=competing).status_code == 409
    samples = wait_all(requests)
    for robot in robots:
        name = robot["id"]
        target = configs[name]["pose_positions"]["inspect"]
        values = samples[name]
        final_error = max(abs(a - b) for a, b in zip(values[-1], target))
        intermediate = any(max(abs(a - b) for a, b in zip(sample, starts[name])) > 0.015 and
                           max(abs(a - b) for a, b in zip(sample, target)) > 0.015 for sample in values)
        assert intermediate, f"No intermediate movement observed for {name}"
        assert final_error < 0.01
        summary["robots"][name] = {"samples": len(values), "intermediate_motion": intermediate,
                                    "final_error_rad": final_error, "action": robot["adapter"]["action"]}
    summary["checks"] += ["live WebSocket snapshots", "same move_named API for both OEMs",
                           "intermediate joint feedback and final positions", "duplicate request idempotency", "busy rejection"]

    demos = [submit(r["id"], "run_demo", {"duration": 2.0}) for r in robots]
    wait_all(demos)
    summary["checks"].append("same three-waypoint run_demo API for both OEMs")

    cancellations = [submit(r["id"], inputs={"pose": "inspect", "duration": 6.0}) for r in robots]
    time.sleep(0.9)
    for robot in robots:
        assert client.post(f"/api/robots/{robot['id']}/stop").json()["accepted"]
    wait_all(cancellations, "canceled")
    held = {r["id"]: r["joint_positions"] for r in state()["robots"]}
    time.sleep(0.6)
    for robot in state()["robots"]:
        drift = max(abs(a - b) for a, b in zip(held[robot["id"]], robot["joint_positions"]))
        assert drift < 0.002
        summary["robots"][robot["id"]]["cancel_hold_drift_rad"] = drift
    summary["checks"].append("confirmed action cancellation and held joint feedback")

    for robot in robots:
        bad = {"id": "bad-" + robot["id"], "type": "move_joints", "robot": robot["id"],
               "actor": "test", "inputs": {"positions": [1000.0] * robot["dof"]}}
        assert client.post("/api/missions", json=bad).status_code == 422
        asset = client.get(robot["urdf_url"])
        assert asset.status_code == 200 and "<robot" in asset.text
    summary["checks"] += ["out-of-limits commands rejected", "official URDFs served"]

    if args.controller_cycle:
        for robot in robots:
            action = robot["adapter"]["action"]
            namespace, controller, _ = action.rsplit("/", 2)

            def switch(field, name=controller):
                request = json.dumps({field: [name], "strictness": 2})
                result = subprocess.run(["ros2", "service", "call", namespace + "/controller_manager/switch_controller",
                                         "controller_manager_msgs/srv/SwitchController", request],
                                        capture_output=True, text=True, timeout=12, check=True)
                assert "ok=True" in result.stdout, result.stdout + result.stderr

            switch("deactivate_controllers")
            try:
                time.sleep(0.8)
                inactive = next(r for r in state()["robots"] if r["id"] == robot["id"])
                assert not inactive["connected"] and not inactive["controller_ready"]
                bad = {"id": "offline-" + robot["id"], "type": "move_named", "robot": robot["id"],
                       "actor": "test", "inputs": {"pose": "ready"}}
                assert client.post("/api/missions", json=bad).status_code == 503
                assert client.post(f"/api/robots/{robot['id']}/stop").status_code == 200
            finally:
                switch("activate_controllers")
            time.sleep(0.8)
            # Lose joint feedback while a real ROS action is executing. The API
            # must fail the mission and request cancellation, not report success.
            moving = submit(robot["id"], inputs={"pose": "inspect", "duration": 10.0})
            time.sleep(0.4)
            switch("deactivate_controllers", "joint_state_broadcaster")
            try:
                wait_all([moving], expected="failed", timeout=8)
                inactive = next(r for r in state()["robots"] if r["id"] == robot["id"])
                assert not inactive["connected"] and inactive["state_age_ms"] >= 1500
            finally:
                switch("activate_controllers", "joint_state_broadcaster")
            time.sleep(0.8)
            restored = next(r for r in state()["robots"] if r["id"] == robot["id"])
            assert restored["connected"]
            time.sleep(0.4)
            stopped = next(r for r in state()["robots"] if r["id"] == robot["id"])
            assert max(abs(a - b) for a, b in zip(restored["joint_positions"], stopped["joint_positions"])) < 0.002
        summary["checks"] += ["real controller deactivation blocks motion while cancel remains callable; reactivation restores readiness",
                               "joint feedback loss during motion fails the mission and cancels the action; held position verified after feedback returns"]

    wait_all([submit(r["id"], inputs={"pose": "ready", "duration": 3.0}) for r in robots])
    summary["timestamp"] = state()["timestamp"]
    output = ROOT / "artifacts" / "integration-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    client.close()


if __name__ == "__main__":
    main()
