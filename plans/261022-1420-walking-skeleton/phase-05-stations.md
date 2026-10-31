---
phase: 5
title: "Stations SPEC to SCHEDULED"
status: done
priority: P1
effort: "1.5d"
dependencies: [2, 3, 4]
---

# Phase 5: Stations SPEC to SCHEDULED

## Goal
One station per transition, real where the spike built it and fake elsewhere, each producing a
valid contract.

## Files to Create / Modify
- Create: `factory/orchestrator/stations.py`: the registry mapping each transition to a station.
- Create: `factory/tools/enrichment.py` (C2, where §15 puts enrichment).
- Create: `factory/workers/voice.py` (A6 fake + C4/C5),
  `visuals.py` (A7/C6 fake), `composer.py` (C7), `render.py` (C8), `tech_checks.py` (C9),
  `packaging.py` (A9 fake), `compliance.py` (A11 code checks), `publisher.py` (C10).
- Modify: `factory/cli.py`: `script` and `review` keep working; their logic moves behind
  functions the stations call, so the CLI and the orchestrator share one path.
- Create: `tests/test_workers.py`.

§15 has no home for the Python side of the deterministic production services (C4-C10), so they
go in a new `factory/workers/`. C7 moves to `studio/` with Remotion in build step 3.

## Tasks & Steps
| Transition | Station | Notes |
|---|---|---|
| SPEC → DRAFTED | A2 | existing `write_script`; fake LLM in e2e |
| DRAFTED → LEVEL_OK | A3 + profiler | existing `level_loop`; an escalated loop moves the episode to `ESCALATED` |
| LEVEL_OK → ENRICHED | C2 | `pack.reading_aids`; empty for `en` and `xx-fixture` |
| ENRICHED → QA_OK | panel | existing `run_panel`; a critical issue sends the episode back to `DRAFTED` once, then escalates |
| QA_OK → SCRIPT_APPROVED | Gate 1 | runner gate |
| → VOICED | A6 + C4/C5 | `VoiceDirectives` from the cast; fake TTS per line; concatenate with pauses into `master.wav`; `AudioManifest` |
| → VISUALS_READY | A7 + C6 | `ShotList` one shot per segment; fake images |
| → RENDERED | C7 + C8 | `RenderProps` is a pure function of Script, AudioManifest and ShotList; FFmpeg renders each shot for its lines' duration with the line text burned in, muxed with `master.wav` |
| → VISUAL_QA_OK | C9 | ffprobe: streams present, 1920×1080, duration within 5% of the manifest |
| → PACKAGED | A9 | `PublishPackage` from the script title and vocab; fake LLM |
| → COMPLIANT | A11 | code checks: MFK flag matches the Audience Profile, synthetic-media flag set |
| → FINAL_APPROVED | Gate 2 | runner gate |
| → UPLOADED | C10 | skip if a receipt exists; else fake upload and store `PublishReceipt` first |
| → SCHEDULED | C10 | set `publish_at` on the receipt |

1. Write C7 as a pure function and test it for byte-identical output on the same inputs (§16).
2. Escape burned-in text for FFmpeg's `drawtext`, or write it to a temp file and use `textfile=`.

## Verification
- `uv run pytest tests/test_workers.py` passes: composer determinism, the render produces an MP4
  that C9 accepts, the publisher refuses a second upload.

## Risk and rollback
Refactoring `factory script`/`review` behind shared functions can change their output; run the
existing CLI tests and one real `factory script` on `en-A2-x01` before and after.
