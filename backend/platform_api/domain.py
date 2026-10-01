"""The public contract and mission record. No ROS or manufacturer imports here."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


Identifier = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")]


class MissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Identifier
    type: Literal["move_named", "move_joints", "run_demo"]
    robot: Identifier
    actor: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    inputs: dict


class Mission(BaseModel):
    id: str
    type: str
    robot: str
    actor: str
    inputs: dict
    status: str = "accepted"
    created_at: str = Field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    progress: float = 0.0
    phase: str = "Queued for local execution"
    detail: str = "Command accepted"


class PlatformError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)
