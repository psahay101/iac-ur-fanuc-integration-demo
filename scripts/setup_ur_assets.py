#!/usr/bin/env python3
"""Export official UR5e assets for HTTP serving; geometry remains unmodified."""

import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory
import xacro


root = Path(__file__).resolve().parents[1]
source = root / "vendor/Universal_Robots_ROS2_Description"
destination = root / "assets/ur"
destination.mkdir(parents=True, exist_ok=True)
share = Path(get_package_share_directory("ur_description"))
xml = xacro.process_file(
    str(share / "urdf/ur.urdf.xacro"),
    mappings={
        "name": "ur5e", "ur_type": "ur5e", "use_fake_hardware": "true",
        "initial_positions_file": str(root / "config/ur_initial_positions.yaml"),
    },
).toprettyxml(indent="  ")
xml = xml.replace("package://ur_description/meshes/ur5e/", "/assets/ur/meshes/")
(destination / "robot.urdf").write_text(xml)
shutil.copytree(source / "meshes/ur5e", destination / "meshes", dirs_exist_ok=True)
shutil.copyfile(source / "LICENSE", destination / "LICENSE")
shutil.copyfile(source / "PINNED_SOURCE.json", destination / "provenance.json")

# Asset generation also verifies config limits/names against the official URDF.
config = json.loads((root / "config/ur.json").read_text())
joints = {joint.attrib["name"]: joint for joint in ET.fromstring(xml).findall("joint")}
for name, expected in zip(config["joint_names"], config["limits"]):
    actual = joints[name].find("limit").attrib
    for field in ("lower", "upper", "velocity"):
        assert abs(float(actual[field]) - expected[field]) < 1e-8, (name, field)
for mesh in ET.fromstring(xml).iter("mesh"):
    path = root / mesh.attrib["filename"].lstrip("/")
    assert path.is_file(), path
print(f"Exported verified UR5e URDF and official meshes to {destination}")
