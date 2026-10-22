---
phase: 3
title: "xx-fixture pack"
status: pending
priority: P2
effort: "0.5d"
dependencies: []
---

# Phase 3: xx-fixture pack

## Goal
A tiny synthetic Language Pack that passes the conformance suite, so the e2e run needs no
spaCy, WordNet or downloaded data.

## Files to Create / Modify
- Create: `packs/xx_fixture/pack.py`: `XxFixturePack` with code `xx-fixture`, whitespace
  tokenizer, a 60-word in-memory wordlist split across A1 and A2, `rate_unit` wpm.
- Create: `packs/xx_fixture/tests/test_conformance.py`
- Modify: `packs/en/tests/test_conformance.py`: move pack-agnostic checks into
  `tests/pack_conformance.py` and run them for both packs.
- Modify: `factory/tools/language_pack.py`: `load_pack` maps `xx-fixture` to `packs.xx_fixture`.
- Create: `config/channels/xx-fixture.yaml`: target pack `xx-fixture`, levels [A2], cast of two,
  format `micro_dialogue`, `budget_usd` 1.
- Create: `evals/xx-fixture/adult/specs/xx-A2-e2e.json` and the canned LLM outputs the fake
  provider returns for it (`tests/fixtures/xx-fixture/`).

The pack code is `xx-fixture` (§15); its Python package is `packs/xx_fixture` because a module
name cannot contain a hyphen.

## Tasks & Steps
1. Extract the shared conformance checks; keep `en`-specific ones (WordNet glosses) in place.
2. Write the pack to pass them with the smallest data.
3. Write a canned A2 draft that passes the profiler on the first try, and canned panel verdicts
   that approve.

## Verification
- `uv run pytest packs` passes for both packs.
- `uv run factory profile` on the canned script passes all gates.

## Risk and rollback
The conformance refactor touches the `en` tests; run them before and after.
