---
phase: 6
title: "End-to-end command and local CI"
status: pending
priority: P1
effort: "0.5d"
dependencies: [5]
---

# Phase 6: End-to-end command and local CI

## Goal
One command runs an episode through the orchestrator, and one script checks the whole repo the
way a hosted CI would.

## Files to Create / Modify
- Modify: `factory/cli.py`: `factory run <spec> [--auto-approve] [--fake-llm]` creates the
  episode row, resolves and stores its config, and calls `Runner.advance`; `factory status <episode>`
  prints the state, jobs and ledger total.
- Create: `scripts/ci.sh`: check `docker`, `ffmpeg`, `ffprobe`; `ruff check`; `pytest` (unit
  and conformance); start `db`, wait for health, migrate a fresh database; run
  `factory run evals/xx-fixture/adult/specs/xx-A2-e2e.json --auto-approve --fake-llm`; assert
  the final state and the MP4; print the elapsed time.
- Create: `tests/test_e2e.py`: marked `e2e`, the same run inside pytest.
- Modify: `README.md`: the Postgres setup, `factory run`, `factory status` and `scripts/ci.sh`.
- Modify: `docs/architecture.md` §17: mark step 0 done with a link to this plan.

## Tasks & Steps
1. `--fake-llm` swaps every role's provider for `FakeLLMProvider`; without it the run uses
   `config/llm.yaml`, so the same command later runs a real `en` episode.
2. Make `ci.sh` exit non-zero on any failure and print which step failed.

## Verification
- `scripts/ci.sh` passes from a clean `docker compose down -v` in under 10 minutes.
- `uv run factory run evals/xx-fixture/adult/specs/xx-A2-e2e.json --fake-llm` without
  `--auto-approve` stops at Gate 1; `factory decide` then `factory run` again finishes.

## Risk and rollback
Docs and a script; revert the commit.
