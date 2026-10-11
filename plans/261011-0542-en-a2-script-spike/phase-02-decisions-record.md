---
phase: 2
title: "Decisions record"
status: pending
priority: P1
effort: "0.5d"
dependencies: [1]
---

# Phase 2: Decisions record

## Goal
Record the launch decisions the spike depends on in the repo, so later phases read them from there and not from chat history.

## Files to Create / Modify
- Create: `docs/decisions/0001-first-slice-and-spike-scope.md`

## Tasks & Steps
1. Write one ADR. For each decision, record the value, the evidence and whether it is decided or deferred:
   - **First slice:** `en` × adult × CEFR A2. Decided by the user on 2026-10-11. Note that this differs from the research.md §A.6 ranking, which put JP-adult first.
   - **Support languages:** `en` and `vi`. For an English target, the `en` gloss is a simple-English definition and `vi` is a full translation. Decided.
   - **Review:** a two-persona agent panel instead of a native human reviewer. Decided. The ADR also records the known risk (the model judges its own family's output), the mitigation (the user spot-checks 2 scripts), and the trigger for revisiting the decision: the panel and the user disagree on either spot-checked script.
   - **Host voice and business model:** deferred.
2. Link the ADR from `README.md`.

## Verification
- Every decision that phase 6 or phase 7 reads has the status `decided`.
