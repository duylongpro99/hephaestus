from typing import Literal

from pydantic import Field

from factory.contracts.base import Contract, Part

Severity = Literal["minor", "major", "critical"]


class QAIssue(Part):
    line_id: str | None  # None for an episode-level issue
    category: str
    severity: Severity
    description: str
    suggested_fix: str | None = None


class QAReport(Contract):
    """A judge's findings on a script (architecture §4.4)."""

    schema_version: str = "1.0.0"
    episode_id: str
    reviewer: str  # persona id, e.g. "examiner" or "learner"
    issues: list[QAIssue] = []
    rubric_scores: dict[str, int] = Field(default_factory=dict)  # 1-5 per rubric item
    hard_gate_failures: list[str] = []
    summary: str = ""

    @property
    def has_critical(self) -> bool:
        return any(issue.severity == "critical" for issue in self.issues)
