---
phase: 4
title: "Episode state machine and runner"
status: done
priority: P1
effort: "1.5d"
dependencies: [1]
---

# Phase 4: Episode state machine and runner

## Goal
Encode the §5 episode states from `SPEC` to `SCHEDULED` as data, and run them as jobs with
retries, budgets, escalation and human-gate waits.

## Files to Create / Modify
- Create: `factory/orchestrator/states.py`: the state enum (including `ESCALATED`,
  `BUDGET_EXCEEDED`, `CANCELLED`), the transition table `state -> (station, next_state)`, and
  which states are human gates (`SCRIPT_APPROVED` = Gate 1, `FINAL_APPROVED` = Gate 2).
- Create: `factory/orchestrator/runner.py`: `Runner(db, stations, store, clock, auto_approve)`
  with `advance(episode_id)` that loops until `SCHEDULED`, a waiting gate, or a stop state.
- Create: `factory/orchestrator/repo.py`: small SQL functions for episodes, jobs, artifacts,
  ledger and gate decisions.
- Create: `tests/test_state_machine.py` (pure, no DB) and `tests/test_runner.py` (marked `db`).

## Tasks & Steps
1. Station interface: `run(ctx) -> StationResult(artifacts, costs, outcome)` where outcome is
   `ok`, `retry`, `escalate` or `fail`. A station reads inputs by artifact pointer, never live
   config; the episode stores its `ResolvedConfig` once at `SPEC` (§4.5).
2. Each step inserts a `job` row (attempt, started/finished, error), writes artifacts through
   the existing `ArtifactStore` and an `artifact` row, appends `cost_ledger` rows, then moves
   `episode.status` in the same transaction.
3. Retries: capped per station with exponential backoff through an injected clock (tests do not
   sleep). After the cap the episode goes to `ESCALATED`.
4. Budget: after every job, if the ledger total exceeds `episode.budget_usd`, stop at
   `BUDGET_EXCEEDED`.
5. Gates: at a gate state the runner stops unless `auto_approve`, which writes a `GateDecision`
   with user `auto` so the e2e run is honest about who approved. `factory decide` (existing)
   also writes the row and the next `advance` continues.
6. Re-running `advance` on a finished step reuses the stored artifact (content addressing), so a
   crash-and-resume costs nothing.

## Verification
- `uv run pytest tests/test_state_machine.py` covers every legal transition, rejects illegal
  ones, retries to escalation and the budget stop.
- `uv run pytest -m db tests/test_runner.py` runs a three-station toy pipeline through the DB,
  including resume after a simulated crash.

## Risk and rollback
New package; nothing existing depends on it.
