from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from factory.contracts.base import Contract

Decision = Literal["approve", "edit-and-approve", "reject"]


class GateDecision(Contract):
    """A review decision at a human gate (architecture §4.4). Gate 1 is script review."""

    schema_version: str = "1.0.0"
    episode_id: str
    gate: Literal[0, 1, 2]
    user: str  # a reviewer persona id, or "human"
    decision: Decision
    diff: str | None = None
    notes: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
