"""The episode state machine from SPEC to SCHEDULED (architecture §5), as data.

Each state names the station that moves an episode out of it. The runner applies the pure
functions here; they decide where a station's outcome sends the episode, so every rule can be
tested without a database.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class State(StrEnum):
    SPEC = "SPEC"
    DRAFTED = "DRAFTED"
    LEVEL_OK = "LEVEL_OK"
    ENRICHED = "ENRICHED"
    QA_OK = "QA_OK"
    SCRIPT_APPROVED = "SCRIPT_APPROVED"
    VOICED = "VOICED"
    VISUALS_READY = "VISUALS_READY"
    RENDERED = "RENDERED"
    VISUAL_QA_OK = "VISUAL_QA_OK"
    PACKAGED = "PACKAGED"
    COMPLIANT = "COMPLIANT"
    FINAL_APPROVED = "FINAL_APPROVED"
    UPLOADED = "UPLOADED"
    SCHEDULED = "SCHEDULED"
    ESCALATED = "ESCALATED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Step:
    station: str
    next: State
    gate: int | None = None  # a human gate: the step waits for a GateDecision
    on_reject: State | None = None  # where a reject sends the episode back to
    max_attempts: int = 3


PIPELINE: dict[State, Step] = {
    State.SPEC: Step("a2_scriptwriter", State.DRAFTED),
    State.DRAFTED: Step("a3_level_editor", State.LEVEL_OK),
    State.LEVEL_OK: Step("c2_enrichment", State.ENRICHED),
    State.ENRICHED: Step("review_panel", State.QA_OK, on_reject=State.DRAFTED),
    State.QA_OK: Step("gate_1", State.SCRIPT_APPROVED, gate=1, on_reject=State.DRAFTED),
    State.SCRIPT_APPROVED: Step("voice", State.VOICED),
    State.VOICED: Step("visuals", State.VISUALS_READY),
    State.VISUALS_READY: Step("render", State.RENDERED),
    State.RENDERED: Step("c9_tech_checks", State.VISUAL_QA_OK),
    State.VISUAL_QA_OK: Step("a9_packager", State.PACKAGED),
    State.PACKAGED: Step("a11_compliance", State.COMPLIANT),
    State.COMPLIANT: Step("gate_2", State.FINAL_APPROVED, gate=2),
    State.FINAL_APPROVED: Step("c10_upload", State.UPLOADED),
    State.UPLOADED: Step("c10_schedule", State.SCHEDULED),
}
DONE = frozenset({State.SCHEDULED})
STOPPED = frozenset({State.ESCALATED, State.BUDGET_EXCEEDED, State.CANCELLED})
GATES = {step.gate: state for state, step in PIPELINE.items() if step.gate}
# A station may send an episode back for a rewrite once; the next reject escalates.
MAX_REJECTS = 1


class IllegalTransition(ValueError):
    pass


def is_legal(src: State, dst: State) -> bool:
    step = PIPELINE.get(src)
    if step is None:  # finished and stopped episodes never move again
        return False
    return dst in (step.next, step.on_reject) or dst in STOPPED


def check_transition(src: State, dst: State) -> None:
    if not is_legal(src, dst):
        raise IllegalTransition(f"{src} -> {dst} is not a legal episode transition")


Outcome = Literal["ok", "retry", "escalate", "fail", "reject"]
JobStatus = Literal["succeeded", "retrying", "escalated", "failed", "rejected"]


@dataclass(frozen=True)
class Move:
    """What the runner does after one attempt: record `job_status`, then retry or go to `to`."""

    job_status: JobStatus
    to: State | None  # None means retry the same step
    backoff_s: float = 0.0


def backoff_s(attempt: int, base_s: float = 1.0) -> float:
    return base_s * 2 ** (attempt - 1)


def after_attempt(state: State, outcome: Outcome, attempt: int, rejects: int) -> Move:
    """Where an attempt's outcome sends the episode. `rejects` counts earlier rejects at this step."""
    step = PIPELINE[state]
    if outcome == "ok":
        return Move("succeeded", step.next)
    if outcome == "retry":
        if attempt < step.max_attempts:
            return Move("retrying", None, backoff_s(attempt))
        return Move("escalated", State.ESCALATED)
    if outcome == "reject":
        if step.on_reject is None:
            if step.gate is not None:  # a human rejected the finished episode: the operator decides what next
                return Move("rejected", State.ESCALATED)
            raise IllegalTransition(f"{step.station} cannot reject")
        if step.gate is None and rejects >= MAX_REJECTS:
            return Move("escalated", State.ESCALATED)
        return Move("rejected", step.on_reject)
    if outcome == "escalate":
        return Move("escalated", State.ESCALATED)
    return Move("failed", State.ESCALATED)


def over_budget(spent_usd: float, budget_usd: float) -> bool:
    return spent_usd > budget_usd
