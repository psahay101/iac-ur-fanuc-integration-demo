"""Load model descriptions. Joint maps and endpoints belong below the API boundary."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate_config(config: dict):
    """Fail early if a new model's joint map or limits are incomplete."""
    names, limits = config["joint_names"], config["limits"]
    if not names or len(set(names)) != len(names) or len(limits) != len(names):
        raise ValueError(f"{config['id']}: unique joint names and one limit per joint required")
    for limit in limits:
        if not all(isinstance(limit[k], (int, float)) and not isinstance(limit[k], bool) and math.isfinite(limit[k])
                   for k in ("lower", "upper", "velocity")):
            raise ValueError(f"{config['id']}: limits must be finite numbers")
        if limit["lower"] >= limit["upper"] or limit["velocity"] <= 0:
            raise ValueError(f"{config['id']}: invalid joint limits")
    poses = config["pose_positions"]
    if {p["id"] for p in config["poses"]} != set(poses) or not config["demo_sequence"]:
        raise ValueError(f"{config['id']}: pose catalog and positions must match")
    if any(p not in poses for p in config["demo_sequence"]):
        raise ValueError(f"{config['id']}: demo references an unknown pose")
    for values in poses.values():
        if len(values) != len(names) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                                          for v in values):
            raise ValueError(f"{config['id']}: pose must have one finite angle per joint")
        if any(not limit["lower"] <= v <= limit["upper"] for v, limit in zip(values, limits)):
            raise ValueError(f"{config['id']}: named pose outside joint limits")
    for endpoint in (config["adapter"]["action"], config["adapter"]["joint_states"]):
        if not endpoint.startswith("/"):
            raise ValueError(f"{config['id']}: ROS endpoints must be absolute")


def load_configs(directory: Path | None = None) -> dict[str, dict]:
    configs = {}
    for path in sorted((directory or ROOT / "config").glob("*.json")):
        config = json.loads(path.read_text())
        if "joint_names" not in config:
            continue
        validate_config(config)
        if config["id"] in configs:
            raise ValueError(f"Duplicate robot id: {config['id']}")
        configs[config["id"]] = config
    if not configs:
        raise RuntimeError("No robot configurations found; run scripts/setup.sh first.")
    return configs


def catalog_entry(config: dict) -> dict:
    return {
        key: config[key] for key in (
            "id", "name", "manufacturer", "model", "description", "accent",
            "urdf_url", "tool_link", "source_url", "joint_names", "limits",
        )
    } | {
        "dof": len(config["joint_names"]),
        "mode": "mock_hardware",
        "capabilities": ["move_named", "move_joints", "run_demo", "stop"],
        "poses": config["poses"],
        "adapter": config["adapter"],
    }
