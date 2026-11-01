from typing import Literal

from pydantic import Field, model_validator

from factory.contracts.base import Contract, Part
from factory.contracts.qa_report import QAIssue


class ReviewerNote(Part):
    """What one reviewer asked to change: a panel persona's issues, or a human's gate notes."""

    reviewer: str  # a panel persona id, or the gate user (e.g. "human")
    gate: Literal[0, 1, 2]
    notes: str = ""  # the reviewer's GateDecision notes
    issues: list[QAIssue] = []  # from the persona's QAReport; empty for a human at a gate

    @property
    def actionable(self) -> bool:
        return bool(self.notes.strip() or self.issues)


class RevisionRequest(Contract):
    """The notes of the latest reject that sent a script back for a rewrite (architecture §5)."""

    schema_version: str = "1.0.0"
    episode_id: str
    round: int = Field(ge=1)  # which rewrite of this episode the notes ask for
    rejected_by: str  # the step that rejected: "review_panel" or "gate_1"
    notes: list[ReviewerNote] = Field(min_length=1)

    @model_validator(mode="after")
    def _has_something_to_fix(self) -> "RevisionRequest":
        if not any(note.actionable for note in self.notes):
            raise ValueError("a revision request needs at least one note or issue to act on")
        return self
