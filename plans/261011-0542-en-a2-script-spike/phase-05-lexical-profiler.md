---
phase: 5
title: "Lexical profiler"
status: pending
priority: P1
effort: "1.5d"
dependencies: [4]
---

# Phase 5: Lexical profiler

## Goal
Build a deterministic profiler that takes a `Script`, an `EpisodeSpec` and a `ResolvedConfig` and returns a `LevelReport` with a pass or fail for each code gate. It uses only the `LanguagePack` interface, so the future `ja` pack can use it unchanged.

## Files to Create / Modify
- Create: `factory/tools/profiler.py`
- Create: `factory/tools/rate_estimator.py`. It estimates duration as speech units divided by the midpoint of the band, plus the sum of `pause_after_ms`. It then checks the estimate against the spec's `length_min`.
- Create: `tests/test_profiler.py`

## Tasks & Steps
1. Compute the in-level ratio over content tokens. Count the spec's target words and review words as in-level. List each off-level token with its line id.
2. Count target-word repetitions by lemma across all lines.
3. Compute sentence-length stats per line and flag the lines outside the band.
4. Read the thresholds from the resolved Level Framework. Do not hard-code any number.
5. Add a CLI command `factory profile <script.json> --spec <spec.json>`. It prints a readable report and writes the `LevelReport` JSON.
6. Write fixture scripts for four cases: a clean pass, a failure caused by one B2 word such as `nevertheless`, too few target-word repetitions, and a script that is too long.

## Verification
- `uv run pytest tests/test_profiler.py` passes.
- Profiling the phase 3 fixture script prints a ratio and the named failures without crashing.
