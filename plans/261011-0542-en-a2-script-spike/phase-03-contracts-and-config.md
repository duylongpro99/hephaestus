---
phase: 3
title: "Contracts and config layers"
status: pending
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 3: Contracts and config layers

## Goal
Define the pydantic contracts and the minimal config layers the spike needs. They match ARCHITECTURE §4, so the later factory can reuse them unchanged.

## Files to Create / Modify
- Create: `factory/contracts/episode_spec.py`: `EpisodeSpec` with the §4.2 fields. `publish_slot` and `season_id` are optional, and `source` is `adhoc`.
- Create: `factory/contracts/script.py`: `Script`, `Segment`, `Line` and `VocabItem`, as in §4.3. `translation` and `gloss` are dicts keyed by support language.
- Create: `factory/contracts/level_report.py`: `LevelReport`, as in §4.4. It holds:
  - the in-level ratio;
  - the off-level tokens;
  - the target-word counts;
  - sentence-length stats;
  - the estimated word count and duration;
  - `gate_failures[]`.
- Create: `factory/contracts/qa_report.py`: `QAReport`, as in §4.4. It holds `issues[{line_id, category, severity, suggested_fix}]`, the rubric scores, `hard_gate_failures[]`, and the `reviewer` persona id.
- Create: `factory/contracts/gate_decision.py`: `GateDecision`, as in §4.4. The decision is approve, edit-and-approve or reject. `user` holds the persona id or `human`.
- Create: `factory/contracts/cost_ledger.py`: one entry per call, with the model, the input, output and cache tokens, and the cost in USD.
- Create: `factory/contracts/__init__.py`: a `schema_version` for each contract.
- Create: `config/frameworks/cefr.yaml`: the A1 and A2 bands, with values from research.md §2.1:
  - in-level ratio ≥0.95;
  - new words ≤5%;
  - each target word repeated ≥5 times;
  - sentence length about 8–12 words at A2 (interpolated between A1 at 6–8 and B1 at 12–15, marked [P]);
  - a rate of 100–120 wpm.
- Create: `config/audiences/adult.yaml`: rate multiplier 1.0, length 6–25 min.
- Create: `config/channels/en-podcast-spike.yaml`: a minimal Channel Bible with a persona, a cast of two, `support_languages: [en, vi]`, and the format `slow_dialogue_explain_replay`.
- Create: `factory/config.py`: merges the layers into a `ResolvedConfig` and sets `config_hash` to the sha256 of its canonical JSON.
- Create: `tests/test_contracts.py`

## Tasks & Steps
1. Write the models and export their JSON Schemas.
2. Write an English version of the §4.2 example spec and the §4.3 example script, and use both as test fixtures.
3. Implement the layer merge, where a later layer overrides an earlier one, and the stable hash.

## Verification
- `uv run pytest tests/test_contracts.py` passes. Both fixtures validate. The hash is the same on every run and changes when any band changes.
