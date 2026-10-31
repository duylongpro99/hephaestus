---
title: "Walking skeleton"
description: "Run one episode from SPEC to SCHEDULED through a Postgres-backed orchestrator, with fake vendors and an FFmpeg placeholder MP4, in one local end-to-end command."
status: completed
priority: P1
effort: 6d
tags: [feature, backend, infra]
blockedBy: []
blocks: []
created: 2026-10-22
---

# Walking skeleton

## Overview

Architecture §17 step 0: prove the assembly line works before any station is good. One episode
moves through every state from `SPEC` to `SCHEDULED` (§5). Each transition is a job, every job
writes the `CostLedger`, and every output lands in the content-addressed artifact store with a
pointer row in Postgres. Stations that already exist (A2, A3, the review panel) are wired in;
the rest are fakes behind real adapter interfaces, so later steps swap a fake for a vendor
without touching the orchestrator.

The EN A2 spike (`plans/261011-0542-en-a2-script-spike/`) built the contracts, the `en` pack,
the profiler, A2, A3 and the panel. Its result was go
(`plans/reports/spike-261011-en-a2-script-results.md`).

## Brainstorm contract

- **Outcome:** `scripts/ci.sh` runs lint, unit tests, pack conformance and an end-to-end episode
  on the `xx-fixture` pack: the episode reaches `SCHEDULED`, `master.mp4` exists and passes the
  tech checks, a fake `PublishReceipt` is stored, all in under 10 minutes with no network.
- **Constraints:**
  - State lives in Postgres, run with Docker Compose (user decision 2026-10-22).
  - The placeholder MP4 is rendered with FFmpeg from Python; Remotion waits for step 3.
  - Jobs run in a synchronous in-process runner over the `job` table; no Redis or worker pool.
  - The repo has no git remote, so "CI" is a local script, written so a hosted runner can call it.
  - Contracts follow §4; layout follows §15; artifacts keep content addressing (principle 5).
  - No secrets in the repo; `DATABASE_URL` comes from the environment or `.env`.
- **Non-goals:**
  - Real TTS, image, publish or notify vendors; the console; C1, C12, C13, C14, C16.
  - Season states and Gate 0. Post-publish states (`PUBLISHED`, `PATCHING`, `RETIRED`).
  - Partial re-render and re-voice of single lines.
- **Acceptance criteria:** see Success Criteria.

## Decisions (user, 2026-10-22)

| Decision | Value |
|---|---|
| State store | Postgres via Docker Compose from the start |
| Placeholder video | FFmpeg called from Python |
| End-to-end scope | `SPEC` → `SCHEDULED`, human gates auto-approved in the e2e run |
| Job queue | Synchronous in-process runner over the `job` table |

## Phases

| # | Phase | Effort | Depends on | Status |
|---|---|---|---|---|
| 1 | [Postgres and migrations](./phase-01-postgres-and-migrations.md) | 1d | none | Pending |
| 2 | [Production contracts and fake adapters](./phase-02-contracts-and-fake-adapters.md) | 1d | none | Pending |
| 3 | [xx-fixture pack](./phase-03-xx-fixture-pack.md) | 0.5d | none | Pending |
| 4 | [Episode state machine and runner](./phase-04-state-machine-and-runner.md) | 1.5d | 1 | Pending |
| 5 | [Stations SPEC to SCHEDULED](./phase-05-stations.md) | 1.5d | 2, 3, 4 | Pending |
| 6 | [End-to-end command and local CI](./phase-06-e2e-and-local-ci.md) | 0.5d | 5 | Pending |

## Success Criteria

- [x] `docker compose up -d db` and `uv run factory db migrate` create the schema; a second
  migrate is a no-op.
- [x] Unit tests cover every legal and illegal transition, retries, budget stop and escalation,
  without a database.
- [x] `xx-fixture` passes the same conformance suite as `en`.
- [x] `uv run factory run <spec> --auto-approve` takes a fixture episode from `SPEC` to
  `SCHEDULED`; each state change is a `job` row; each artifact has an `artifact` row whose hash
  matches the store.
- [x] `master.mp4` passes C9: video and audio streams present, duration within 5% of the
  `AudioManifest` total.
- [x] Re-running the same episode does not upload twice (the receipt check holds).
- [x] Without `--auto-approve` the run stops at `SCRIPT_APPROVED`'s gate and resumes after
  `factory decide`.
- [x] `scripts/ci.sh` passes end to end in under 10 minutes with the network off for LLM calls.

## Risks

| Risk | Mitigation |
|---|---|
| Postgres makes the e2e slow or flaky | One compose service with a healthcheck; tests use a throwaway database per run |
| Fakes drift from real vendors' shapes | Fakes implement the same adapter protocols the real ones will; contracts validate every boundary |
| The runner hides failures in retries | Retries are capped per station; the final error and attempt count are stored on the `job` row |
| FFmpeg missing on a hosted runner | `ci.sh` checks for `ffmpeg`/`ffprobe` first and names the missing tool |
