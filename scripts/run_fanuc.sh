#!/usr/bin/env bash
# Run only the project's pinned FANUC build on the system Humble installation.
set -eo pipefail
platform_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH ROS_PACKAGE_PATH
source /opt/ros/humble/setup.bash
source "$platform_dir/.runtime/fanuc_ws/install/local_setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-71}"
export ROS_LOCALHOST_ONLY=1
export ROS_LOG_DIR="$platform_dir/.runtime/logs/fanuc"
mkdir -p "$ROS_LOG_DIR"
exec ros2 launch "$platform_dir/ros/fanuc_mock.launch.py"
