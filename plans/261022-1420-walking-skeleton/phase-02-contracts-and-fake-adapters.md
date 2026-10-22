---
phase: 2
title: "Production contracts and fake adapters"
status: pending
priority: P1
effort: "1d"
dependencies: []
---

# Phase 2: Production contracts and fake adapters

## Goal
Add the §4.4 contracts the stations after `SCRIPT_APPROVED` exchange, and adapter protocols
with fake implementations that need no network.

## Files to Create / Modify
- Create: `factory/contracts/voice_directives.py`, `audio_manifest.py`, `shot_list.py`,
  `render_props.py`, `publish_package.py`, `publish_receipt.py`: fields from §4.4, each with
  `schema_version = "1.0.0"`.
- Modify: `factory/contracts/__init__.py`; regenerate `factory/contracts/schemas/`.
- Create: `factory/adapters/tts/base.py` (`TTSProvider.synthesize(text, voice, rate, out_path) -> duration_s`)
  and `factory/adapters/tts/fake.py`: FFmpeg sine tone whose length is the pack's
  `speech_units` divided by the rate.
- Create: `factory/adapters/image/base.py` and `fake.py`: a solid-colour 1920×1080 PNG per shot.
- Create: `factory/adapters/publish/base.py` and `fake.py`: writes the upload to a local
  directory and returns a fake video id derived from the file hash.
- Create: `factory/adapters/llm/fake.py`: `FakeLLMProvider` implementing `LLMProvider`, which
  returns canned outputs per station from fixture JSON and records zero-cost `CostEntry`s.
- Create: `tests/test_fake_adapters.py`.

## Tasks & Steps
1. Write the contracts; keep them minimal but valid for the real vendors later (per-line
   entries keyed by line id, uris relative to the artifact store).
2. Write the protocols first, then the fakes. Fakes are deterministic: the same input gives
   byte-identical output.
3. `FakeLLMProvider.structured()` validates its canned output against the requested model, so a
   contract change breaks the fixture loudly.

## Verification
- `uv run python -m factory.contracts` regenerates schemas; the contract test passes.
- `uv run pytest tests/test_fake_adapters.py` passes, including a determinism check.

## Risk and rollback
Additive files only.
