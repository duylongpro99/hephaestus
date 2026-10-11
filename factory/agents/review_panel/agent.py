"""Two-persona review panel: independent judges with opposite priorities (ADR 0001, decision 3).

Each persona gets its own call with only the spec and the finished script. Neither sees the
other's verdict or the Level Editor's reasoning. Each returns a QAReport and a GateDecision;
the decision rules below are enforced in code, not left to the model.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from factory.adapters.llm.anthropic_client import LLMClient
from factory.artifacts import station_version
from factory.contracts import CostEntry, EpisodeSpec, GateDecision, QAIssue, QAReport, Script
from factory.contracts.qa_report import Severity

HERE = Path(__file__).resolve().parent
PERSONAS = {
    "examiner": HERE / "persona_examiner.md",
    "learner": HERE / "persona_learner.md",
}
SCRIPT_REVIEW_GATE = 1


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PanelIssue(_Closed):
    line_id: str | None
    category: str
    severity: Severity
    description: str
    suggested_fix: str | None


class RubricScore(_Closed):
    name: str
    score: int = Field(ge=1, le=5)


class PanelVerdict(_Closed):
    """What one reviewer returns (LLM-facing; closed objects only)."""

    issues: list[PanelIssue]
    rubric_scores: list[RubricScore]
    level_fit_verdict: Literal["below", "at", "above"]
    hard_gate_failures: list[str]
    decision: Literal["approve", "edit-and-approve", "reject"]
    summary: str


@dataclass
class Review:
    persona: str
    qa_report: QAReport
    decision: GateDecision
    level_fit_verdict: str
    cost: CostEntry | None = None

    @property
    def approved(self) -> bool:
        return self.decision.decision in ("approve", "edit-and-approve")


def station(persona: str) -> str:
    return f"review_{persona}"


def version(persona: str, model: str) -> str:
    return station_version(model, PERSONAS[persona], Path(__file__).resolve())


def enforce_rules(verdict: PanelVerdict) -> str:
    """A critical issue forces a reject; a major issue rules out a plain approve."""
    severities = {issue.severity for issue in verdict.issues}
    if "critical" in severities:
        return "reject"
    if verdict.decision == "approve" and "major" in severities:
        return "edit-and-approve"
    return verdict.decision


def to_review(verdict: PanelVerdict, persona: str, episode_id: str, cost: CostEntry | None = None) -> Review:
    report = QAReport(
        episode_id=episode_id,
        reviewer=persona,
        issues=[QAIssue(**issue.model_dump()) for issue in verdict.issues],
        rubric_scores={s.name: s.score for s in verdict.rubric_scores},
        hard_gate_failures=verdict.hard_gate_failures,
        summary=verdict.summary,
    )
    decision = enforce_rules(verdict)
    fixes = [f"{i.line_id or 'episode'}: {i.suggested_fix}" for i in verdict.issues if i.suggested_fix]
    notes = verdict.summary
    if decision != verdict.decision:
        notes += f" [decision changed from {verdict.decision} by the panel rules]"
    gate_decision = GateDecision(
        episode_id=episode_id,
        gate=SCRIPT_REVIEW_GATE,
        user=persona,
        decision=decision,
        diff="\n".join(fixes) or None,
        notes=notes,
    )
    return Review(persona=persona, qa_report=report, decision=gate_decision,
                  level_fit_verdict=verdict.level_fit_verdict, cost=cost)


def build_user(spec: EpisodeSpec, script: Script) -> str:
    return (
        f"Review this episode script for adult learners at CEFR {spec.level}.\n\n"
        f"Episode Spec (theme, target words, review words, grammar point):\n"
        f"{spec.model_dump_json(include={'level', 'theme', 'target_words', 'review_words', 'grammar_point', 'length_min'})}\n\n"
        f"Script (the `vi` text is the Vietnamese translation; `gloss.en` is a simple-English gloss):\n"
        f"{script.model_dump_json(exclude={'schema_version'})}"
    )


def review(persona: str, spec: EpisodeSpec, script: Script, llm: LLMClient) -> Review:
    system = [{"type": "text", "text": PERSONAS[persona].read_text(encoding="utf-8"),
               "cache_control": {"type": "ephemeral"}}]
    result = llm.structured(
        station=station(persona), system=system, user=build_user(spec, script),
        output_model=PanelVerdict, effort="high", max_tokens=32_000,
    )
    return to_review(result.parsed, persona, spec.episode_id, result.cost)


def run_panel(spec: EpisodeSpec, script: Script, llm: LLMClient) -> list[Review]:
    """Both personas, each in its own independent call."""
    return [review(persona, spec, script, llm) for persona in PERSONAS]
