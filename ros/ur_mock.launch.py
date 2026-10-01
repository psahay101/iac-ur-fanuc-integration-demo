"""Headless, namespaced version of the official UR driver mock launch path.

The robot and hardware definition come from ur_description; controller settings
come from ur_robot_driver. Only the launch wiring is local. GenericSystem mirrors
controller commands, so this validates ROS integration, not UR network protocols.
"""

from pathlib import Path
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
import xacro
import yaml


def generate_launch_description():
    root = Path(__file__).resolve().parents[1]
    description_share = Path(get_package_share_directory("ur_description"))
    driver_share = Path(get_package_share_directory("ur_robot_driver"))
    description = xacro.process_file(
        str(description_share / "urdf/ur.urdf.xacro"),
        mappings={
            "name": "ur5e",
            "ur_type": "ur5e",
            "use_fake_hardware": "true",
            "initial_positions_file": str(root / "config/ur_initial_positions.yaml"),
        },
    ).toxml()

    # Upstream YAML is for a single robot at /. Namespace its node keys without
    # altering upstream joint/controller settings so both OEMs can run together.
    upstream = (driver_share / "config/ur_controllers.yaml").read_text()
    settings = yaml.safe_load(upstream.replace("$(var tf_prefix)", ""))
    selected = {key: settings[key] for key in (
        "controller_manager", "joint_trajectory_controller"
    )}
    selected["controller_manager"]["ros__parameters"]["update_rate"] = 100
    namespaced = {f"/ur/{key}": value for key, value in selected.items()}
    # ros2_control passes this file to the controllers it loads.
    with tempfile.NamedTemporaryFile(mode="w", prefix="iac_ur_", suffix=".yaml", delete=False) as file:
        yaml.safe_dump(namespaced, file)
        controller_file = file.name

    robot_description = {"robot_description": description}
    return LaunchDescription([
        Node(
            package="controller_manager", executable="ros2_control_node",
            namespace="ur", parameters=[robot_description, controller_file],
            output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            namespace="ur", parameters=[robot_description], output="screen",
            remappings=[("/tf", "/ur/tf"), ("/tf_static", "/ur/tf_static")],
        ),
        Node(
            package="controller_manager", executable="spawner", namespace="ur",
            arguments=["joint_state_broadcaster", "joint_trajectory_controller",
                       "--controller-manager", "/ur/controller_manager",
                       "--controller-manager-timeout", "30"],
            output="screen",
        ),
    ])
