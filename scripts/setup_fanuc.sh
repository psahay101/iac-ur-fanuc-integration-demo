#!/usr/bin/env bash
# Build the bundled, pinned FANUC sources without fetching repositories.
# Prerequisites: ROS 2 Humble, ros2_control/controllers, colcon, CMake, g++.
set -eo pipefail
platform_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$platform_dir/.runtime/fanuc_ws"
driver="$platform_dir/vendor/fanuc_driver"
description="$platform_dir/vendor/fanuc_description"
deps="$driver/fanuc_libs/dependencies"
mkdir -p "$workspace"
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH ROS_PACKAGE_PATH
source /opt/ros/humble/setup.bash
# The bundled OEM controller carries the recorded compatibility patch for this API.
controller_header=/opt/ros/humble/include/joint_trajectory_controller/joint_trajectory_controller/joint_trajectory_controller.hpp
if ! grep -q 'RealtimeBuffer<bool> rt_has_pending_goal_' "$controller_header"; then
    echo 'Update ros-humble-ros2-controllers: the bundled compatibility patch targets the current Humble RealtimeBuffer API.' >&2
    exit 1
fi
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
export MAKEFLAGS="-j${CMAKE_BUILD_PARALLEL_LEVEL}"
cd "$workspace"
# FANUC's normal build fetches Git submodules and applies its own dependency
# patches. The distribution bundles those same pinned sources already patched.
colcon build --base-paths "$driver" "$description" \
    --symlink-install --packages-up-to fanuc_controllers fanuc_crx_description \
    --executor sequential --cmake-args \
    -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release \
    -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
    -DFETCHCONTENT_SOURCE_DIR_SOCKPP="$deps/sockpp" \
    -DFETCHCONTENT_SOURCE_DIR_READERWRITERQUEUE="$deps/readerwriterqueue" \
    -DFETCHCONTENT_SOURCE_DIR_REFLECT-CPP="$deps/reflect-cpp" \
    -DFETCHCONTENT_SOURCE_DIR_YAML-CPP="$deps/yaml-cpp"
source "$workspace/install/local_setup.bash"
python3 "$platform_dir/scripts/setup_fanuc_assets.py"
