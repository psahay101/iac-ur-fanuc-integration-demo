#!/usr/bin/env bash
set -eo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH ROS_PACKAGE_PATH
source /opt/ros/humble/setup.bash
export PYTHONPATH="$project_root/backend:$PYTHONPATH"
export PYTHONNOUSERSITE=1
export ROS_LOG_DIR="$project_root/.runtime/logs/api"
mkdir -p "$ROS_LOG_DIR"
exec "$project_root/.venv/bin/python" -m uvicorn platform_api.app:app --host 127.0.0.1 --port 8000 --no-access-log
