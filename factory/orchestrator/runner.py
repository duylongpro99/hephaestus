"""Synchronous in-process runner: moves one episode through the state machine as jobs.

Each attempt at a step runs its station, then records in one transaction the job row, the
artifact pointers, the cost ledger rows and the state change. Station outputs live in the
content-addressed store, so re-running a finished step after a crash reuses them for free.
"""

import itertools
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cached_property
from typing import Callable, Protocol

import psycopg

from factory.adapters.llm.base import LLMError
from factory.artifacts import M, ArtifactStore, Producer, load
from factory.config import ResolvedConfig
from factory.contracts import CostEntry, EpisodeSpec, GateDecision
from factory.orchestrator import repo
from factory.orchestrator.states import (
    DONE, MAX_REWRITES, PIPELINE, STOPPED, Move, Outcome, State, Step, after_attempt, over_budget,
)
from factory.tools.language_pack import LanguagePack, load_pack

AUTO_USER = "auto"


class EpisodeBusy(RuntimeError):
    """Another runner is advancing the episode; running it twice would pay and upload twice."""


class Clock(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class StationResult:
    outcome: Outcome = "ok"
    error: str | None = None
    gate_decisions: list[GateDecision] = field(default_factory=list)  # reviewer verdicts to record


class StationContext(Producer):
    """What a station sees: the pinned spec and config, earlier artifacts by pointer, and the store."""

    def __init__(self, conn: psycopg.Connection, store: ArtifactStore, episode: dict, clock: Clock):
        self.spec = EpisodeSpec.model_validate(episode["spec"])
        self.config = ResolvedConfig.model_validate(episode["resolved_config"])
        super().__init__(store, self.spec.channel, self.spec.episode_id, self.spec.season_id)
        self.conn, self.clock = conn, clock

    @cached_property
    def pack(self) -> LanguagePack:
        return load_pack(self.config.pack.code)

    def envelope(self, station: str) -> dict:
        row = repo.latest_artifact(self.conn, self.episode, station)
        if row is None:
            raise LookupError(f"episode {self.episode} has no {station} artifact yet")
        return self.store.read(row["uri"])

    def read(self, station: str, model: type[M]) -> M:
        """The latest artifact a station wrote for this episode."""
        return load(model, self.envelope(station)["artifact"])


Station = Callable[[StationContext], StationResult]


def rejected_error(outcome: Outcome, move: Move, reason: str | None) -> str | None:
    """The job error: a reject that escalates says the rewrite budget ran out, then why it was rejected."""
    if outcome == "reject" and move.job_status == "escalated":
        return f"rewrite limit reached ({MAX_REWRITES} of {MAX_REWRITES}): {reason or 'no reason given'}"
    return reason


class Runner:
    def __init__(self, conn: psycopg.Connection, stations: dict[str, Station], store: ArtifactStore,
                 clock: Clock | None = None, auto_approve: bool = False, panel_users: tuple[str, ...] = ()):
        self.conn, self.stations, self.store = conn, stations, store
        self.clock = clock or SystemClock()
        self.auto_approve = auto_approve
        self.panel_users = panel_users  # their gate-1 verdicts advise; they never open a human gate

    def advance(self, episode_id: str) -> State:
        """Run steps until the episode is SCHEDULED, waits at a human gate, or stops.

        Holds a Postgres advisory lock on the episode for the whole run, so two runners never
        advance the same episode at once.
        """
        locked = self.conn.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (episode_id,)).fetchone()["ok"]
        if not locked:
            raise EpisodeBusy(f"another runner is advancing {episode_id}")
        try:
            return self._advance(episode_id)
        finally:
            self.conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (episode_id,))

    def _advance(self, episode_id: str) -> State:
        while True:
            episode = repo.get_episode(self.conn, episode_id)
            if episode is None:
                raise LookupError(f"no episode {episode_id}")
            state = State(episode["status"])
            if state in DONE or state in STOPPED or self._stop_if_over_budget(episode, state):
                return State(repo.get_episode(self.conn, episode_id)["status"])
            step = PIPELINE[state]
            if step.gate is not None:
                if not self._pass_gate(episode, state, step):
                    return state
            else:
                self._run_step(episode, state, step)

    def _pass_gate(self, episode: dict, state: State, step: Step) -> bool:
        decision = repo.gate_decision_since(self.conn, episode["id"], step.gate, episode["status_changed_at"],
                                            self.panel_users)
        if decision is None and self.auto_approve:
            auto = GateDecision(episode_id=episode["id"], gate=step.gate, user=AUTO_USER, decision="approve",
                                notes="approved by `factory run --auto-approve`", timestamp=self.clock.now())
            with self.conn.transaction():
                repo.insert_gate_decision(self.conn, auto)
            decision = {"decision": auto.decision, "notes": auto.notes, "ts": auto.timestamp}
        if decision is None:
            return False
        outcome: Outcome = "reject" if decision["decision"] == "reject" else "ok"
        attempt = repo.count_jobs(self.conn, episode["id"], step.station) + 1
        move = after_attempt(state, outcome, attempt, repo.count_rewrites(self.conn, episode["id"]))
        error = rejected_error(outcome, move, decision["notes"]) if outcome == "reject" else None
        with self.conn.transaction():
            repo.insert_job(self.conn, episode=episode["id"], station=step.station, from_status=state,
                            to_status=move.to, attempt=attempt, status=move.job_status, started_at=decision["ts"],
                            finished_at=self.clock.now(), error=error)
            repo.move(self.conn, episode["id"], state, move.to, self.clock.now())
        return True

    def _run_step(self, episode: dict, state: State, step: Step) -> None:
        station = self.stations[step.station]
        earlier = repo.count_jobs(self.conn, episode["id"], step.station)
        rewrites = repo.count_rewrites(self.conn, episode["id"])
        # Retries of this step since the episode reached it count towards the cap, across restarts.
        retried = repo.count_jobs(self.conn, episode["id"], step.station, "retrying", since=episode["status_changed_at"])
        for attempt in itertools.count(retried + 1):
            ctx = StationContext(self.conn, self.store, episode, self.clock)
            started = self.clock.now()
            costs: list[CostEntry] = []  # billed by calls that produced no artifact
            try:
                result = station(ctx)
            except LLMError as exc:
                costs += exc.costs
                result = StationResult("retry", str(exc))
            except Exception as exc:  # a station bug or a vendor failure: retry, then escalate with the error
                costs += getattr(exc, "costs", [])  # a media failure carries what earlier requests billed
                result = StationResult("retry", f"{type(exc).__name__}: {exc}")
            move = after_attempt(state, result.outcome, attempt, rewrites)
            error = rejected_error(result.outcome, move, result.error)
            with self.conn.transaction():
                for produced in ctx.produced:
                    # An artifact's cost is counted once, when the episode first points at it: an output a
                    # crashed attempt paid for is charged on resume, and a reused one is never charged twice.
                    if repo.insert_artifact(self.conn, episode["id"], produced.envelope, self.store.uri(produced.path)):
                        costs += [CostEntry.model_validate(c) for c in produced.envelope.get("cost", [])]
                repo.add_costs(self.conn, episode["id"], costs)
                for decision in result.gate_decisions:
                    repo.insert_gate_decision(self.conn, decision)
                repo.insert_job(self.conn, episode=episode["id"], station=step.station, from_status=state,
                                to_status=move.to, attempt=earlier + attempt - retried, status=move.job_status,
                                started_at=started, finished_at=self.clock.now(), error=error)
                if move.to is not None:
                    repo.move(self.conn, episode["id"], state, move.to, self.clock.now())
            current = move.to or state
            if self._stop_if_over_budget(episode, current) or move.to is not None:
                return
            self.clock.sleep(move.backoff_s)

    def _stop_if_over_budget(self, episode: dict, state: State) -> bool:
        spent, budget = repo.spent_usd(self.conn, episode["id"]), float(episode["budget_usd"])
        if state in DONE or state in STOPPED or not over_budget(spent, budget):
            return False
        now = self.clock.now()
        with self.conn.transaction():
            repo.insert_job(self.conn, episode=episode["id"], station="budget", from_status=state,
                            to_status=State.BUDGET_EXCEEDED, attempt=1, status="failed", started_at=now,
                            finished_at=now, error=f"spent ${spent:.4f} of the ${budget:.2f} budget")
            repo.move(self.conn, episode["id"], state, State.BUDGET_EXCEEDED, now)
        return True
