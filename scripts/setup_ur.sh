#!/usr/bin/env bash
# Build the pinned official UR packages in an isolated local workspace.
set -eo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH ROS_PACKAGE_PATH
source /opt/ros/humble/setup.bash

mkdir -p "$project_root/.runtime/ur_ws"
cd "$project_root/.runtime/ur_ws"
export MAKEFLAGS="-j${IAC_BUILD_JOBS:-2}"
colcon build \
  --base-paths "$project_root/vendor/Universal_Robots_ROS2_Driver" "$project_root/vendor/Universal_Robots_ROS2_Description" \
  --packages-up-to ur_robot_driver --executor sequential \
  --cmake-args -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
  --event-handlers desktop_notification-

source install/local_setup.bash
/usr/bin/python3 "$project_root/scripts/setup_ur_assets.py"
