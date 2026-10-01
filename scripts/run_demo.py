"""Launch only this demo's processes; Ctrl+C cleans up their process groups."""

import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    lock = (runtime / "run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("This demo is already running. Stop its terminal before starting another copy.")
    if not (ROOT / "frontend/dist/index.html").exists():
        sys.exit("Frontend build missing. Run bash scripts/setup.sh first.")
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", 8000))
        except OSError:
            sys.exit("Port 8000 is occupied. Stop the other application before starting this demo.")
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID=env.get("IAC_ROS_DOMAIN_ID", "71"), ROS_LOCALHOST_ONLY="1")
    logs = runtime / "logs"
    logs.mkdir(exist_ok=True)
    processes, handles = [], []

    def shutdown(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        for name in ("ur", "fanuc", "api"):
            handle = (logs / f"{name}.log").open("w")
            handles.append(handle)
            child = subprocess.Popen(["bash", str(ROOT / "scripts" / f"run_{name}.sh")],
                                     cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            processes.append((name, child))
        print(f"Starting official ROS 2 stacks (mock hardware), domain {env['ROS_DOMAIN_ID']}…", flush=True)
        deadline = time.monotonic() + 90
        ready = False
        while True:
            for name, child in processes:
                if child.poll() is not None:
                    raise RuntimeError(f"{name} exited with code {child.returncode}. See {logs / (name + '.log')}")
            if not ready:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1) as response:
                        ready = json.load(response)["status"] == "ready"
                except (OSError, ValueError):
                    pass
                if ready:
                    print("Both arms ready. Open http://localhost:8000\nCtrl+C stops this demo. Logs: .runtime/logs", flush=True)
                elif time.monotonic() > deadline:
                    raise RuntimeError(f"ROS controllers did not become ready in 90 seconds. Check {logs}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping the demo…", flush=True)
    finally:
        # Ask the API to cancel first, then shut down only children we launched.
        ordered = list(reversed(processes))
        for _, child in ordered:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
        for handle in handles:
            handle.close()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        sys.exit(str(error))
