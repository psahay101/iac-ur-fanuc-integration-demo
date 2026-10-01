"""Export official FANUC CRX-10iA assets with browser-resolvable mesh URLs.

Geometry and kinematics are unchanged. The same OEM xacro used by ROS produces
the browser URDF; only mesh resource paths and the generated header are changed.
"""

import json
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

import xacro
from ament_index_python.packages import get_package_share_directory


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor"
OUTPUT = ROOT / "assets/fanuc"


def main():
    share = Path(get_package_share_directory("fanuc_hardware_interface"))
    description = xacro.process_file(
        str(share / "robot/crx10ia.urdf.xacro"),
        mappings={"use_mock": "true", "robot_ip": "1.1.1.1"},
    ).toxml()
    robot = ET.fromstring(description)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for mesh in robot.findall(".//mesh"):
        filename = mesh.attrib["filename"]
        package, relative = filename.removeprefix("package://").split("/", 1)
        source = Path(get_package_share_directory(package)) / relative
        if source.read_bytes().startswith(b"version https://git-lfs.github.com/spec/"):
            raise RuntimeError(f"Mesh is a Git LFS pointer; fetch its content: {source}")
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        mesh.set("filename", "/assets/fanuc/" + relative)
    ET.indent(robot)
    (OUTPUT / "robot.urdf").write_text(
        '<?xml version="1.0"?>\n<!-- Generated from official FANUC CRX-10iA xacro. See provenance.json. -->\n'
        + ET.tostring(robot, encoding="unicode") + "\n"
    )
    shutil.copytree(SOURCE / "fanuc_description/LICENSES", OUTPUT / "LICENSES", dirs_exist_ok=True)
    sources = json.loads((SOURCE / "fanuc_sources.json").read_text())
    provenance = {
        "model": "FANUC CRX-10iA",
        "license": "Apache-2.0",
        "repositories": sources["repositories"],
        "modifications": "Expanded official Xacro; replaced package mesh paths with web asset paths. Geometry and meshes unchanged.",
        "driver_compatibility_patch": "ros/fanuc_humble_realtime_buffer.patch adapts two upstream controller flags to Humble joint_trajectory_controller 2.45 RealtimeBuffer accessors. The FANUC scaled controller still executes trajectories.",
        "simulation": "FANUC ScaledJointTrajectoryController with the official Xacro's mock_components/GenericSystem; no physical controller or ROBOGUIDE validation.",
    }
    (OUTPUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    names = [f"J{i}" for i in range(1, 7)]
    limits = []
    for name in names:
        limit = robot.find(f"./joint[@name='{name}']/limit")
        limits.append({key: float(limit.attrib[key]) for key in ("lower", "upper", "velocity")})
    config = {
        "id": "fanuc", "name": "FANUC CRX-10iA", "manufacturer": "FANUC", "model": "CRX-10iA",
        "description": "Six-axis collaborative arm · official FANUC ROS 2 stack",
        "accent": "#ffd34e", "dof": 6, "mode": "mock_hardware",
        "urdf_url": "/assets/fanuc/robot.urdf", "tool_link": "end_effector",
        "source_url": "https://github.com/FANUC-CORPORATION/fanuc_driver",
        "joint_names": names, "limits": limits,
        "poses": [{"id": "ready", "label": "Ready"}, {"id": "inspect", "label": "Inspect"},
                  {"id": "park", "label": "Park"}],
        "pose_positions": {"ready": [0.0, -0.45, 0.55, 0.0, 0.7, 0.0],
                  "inspect": [0.65, 0.05, 0.8, 0.5, 0.8, -0.4],
                  "park": [-0.35, -0.35, 1.1, 0.0, 0.9, 0.0]},
        "initial_positions": [0.0] * 6,
        "demo_sequence": ["inspect", "park", "ready"],
        "capabilities": ["move_named", "move_joints", "run_demo", "stop"],
        "adapter": {"name": "FANUC ROS 2 adapter", "action": "/fanuc/joint_trajectory_controller/follow_joint_trajectory",
                    "joint_states": "/fanuc/joint_states"},
    }
    (ROOT / "config/fanuc.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"Exported FANUC URDF, 14 OEM meshes, license, provenance and configuration to {OUTPUT}")


if __name__ == "__main__":
    main()
