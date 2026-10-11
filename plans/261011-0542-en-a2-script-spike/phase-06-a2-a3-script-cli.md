---
phase: 6
title: "Specs, A2 Scriptwriter and A3 loop CLI"
status: pending
priority: P1
effort: "2.5d"
dependencies: [2, 5]
---

# Phase 6: Specs, A2 Scriptwriter and A3 loop CLI

## Goal
Turn one spec into one script with a single CLI command. A2 drafts the script, the profiler checks it, and A3 patches it for up to 4 turns, then either passes or escalates. Every run is stored as a hashed artifact together with its cost.

## Files to Create / Modify
- Create: `evals/en/adult/specs/en-A2-x01.json` … `en-A2-x10.json`. These are 10 hand-curated ad-hoc specs. Each has a distinct everyday adult theme, 5–8 A2 target words from `lexicon.jsonl`, A1 review words, one A2 grammar point (for example past continuous, `going to`, comparatives, or present perfect with `ever`), and a length of 6–8 minutes.
- Create: `factory/adapters/llm/anthropic_client.py`: a thin wrapper that returns the parsed output plus a `CostLedger` entry.
- Create: `factory/agents/a2_scriptwriter/`: `prompt.md`, `agent.py` and one few-shot example.
- Create: `factory/agents/a3_level_editor/`: `prompt.md` and `agent.py`, plus these tools:
  - `lexical_profile`: the phase 5 profiler.
  - `rate_estimate`.
  - `find_simpler_synonym`: calls `EnPack.simpler_synonyms`.
- Create: `factory/artifacts.py`. It writes each artifact to `artifacts/{channel}/adhoc/{episode}/{station}@{hash}.json`. The hash covers the inputs and the `station_version`, which is the prompt hash, model id and code version.
- Create: `factory/cli.py`. The command `factory script <spec.json>` runs A2, then the profiler, then A3 if needed. It prints the gate status, the number of A3 turns and the USD cost.
- Create: `tests/test_artifacts.py`

## Tasks & Steps
1. Load the `claude-api` skill. Confirm the current model ID, `messages.parse`, Tool Runner and prompt caching. The default model is the latest Opus, which on 2026-10-11 is `claude-opus-5-5`.
2. Order the prompt prefix as in §8, from most stable to least:
   1. the system prompt;
   2. the ResolvedConfig;
   3. the A1/A2 lexicon excerpt and the grammar list;
   4. the few-shot example;
   5. a cache breakpoint;
   6. the spec.

   Keep timestamps out of the prefix.
3. A2 makes one structured call that returns a `Script`. Each line carries a `vi` translation. Each vocab item carries a simple `en` gloss and a `vi` gloss.
4. A3 runs a Tool Runner loop of at most 4 turns and edits only the lines the gates flagged. If the gates still fail after 4 turns, the state becomes `ESCALATED` and the last `LevelReport` is kept.
5. Read the API key only from `ANTHROPIC_API_KEY`. `.env` stays gitignored.
6. Unit-test the artifact hashing and `station_version` without any network calls.

## Verification
- `uv run pytest tests/test_artifacts.py` passes.
- `uv run factory script evals/en/adult/specs/en-A2-x01.json` ends with the gates passed or with `ESCALATED`. It reports the turn count and the USD cost, and `cache_read_input_tokens` is above 0 on the second call.
