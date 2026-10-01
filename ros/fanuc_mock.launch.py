"""Headless FANUC bringup: official CRX description, mock hardware and controller.

Only launch composition belongs here. Motion execution is provided by FANUC's
ScaledJointTrajectoryController and the official xacro's GenericSystem mock.
"""

from pathlib import Path

import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("fanuc_hardware_interface"))
    description = xacro.process_file(
        str(share / "robot" / "crx10ia.urdf.xacro"),
        mappings={"use_mock": "true", "robot_ip": "1.1.1.1"},
    ).toxml()
    parameters = {"robot_description": description}
    controller_config = Path(__file__).resolve().parent / "fanuc_controllers.yaml"
    return LaunchDescription([
        Node(
            package="controller_manager", executable="ros2_control_node",
            namespace="fanuc", parameters=[parameters, str(controller_config)],
            output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            namespace="fanuc", parameters=[parameters], output="screen",
            remappings=[("/tf", "tf"), ("/tf_static", "tf_static")],
        ),
        Node(
            package="controller_manager", executable="spawner",
            arguments=["joint_state_broadcaster", "joint_trajectory_controller",
                       "--controller-manager", "/fanuc/controller_manager",
                       "--controller-manager-timeout", "60"],
            output="screen",
        ),
    ])
