---
title: Walking skeleton implemented
date: 2026-10-22
summary: One xx-fixture episode runs SPEC to SCHEDULED on Postgres with fake vendors; scripts/ci.sh passes in about 22 seconds
---

# Walking skeleton implemented

## What happened
- Implemented `plans/261022-1420-walking-skeleton/`: Postgres via `compose.yaml`, SQL migrations
  (`factory db migrate`), the §5 state machine as data (`factory/orchestrator/states.py`), a
  synchronous runner with per-episode advisory lock, retries, budget stop and human gates, and one
  station per transition (`factory/orchestrator/stations.py`, `factory/workers/`).
- New contracts: VoiceDirectives, AudioManifest, ShotList, RenderProps, PublishPackage,
  PublishReceipt, plus Enrichment (C2) and RenderedVideo (C8).
- `xx-fixture` pack (60 invented words) passes the shared conformance suite now in
  `tests/pack_conformance.py`, which `en` also runs.
- `factory run <spec> [--auto-approve] [--fake-llm]`, `factory status`, and `factory decide --gate`
  now writes to the database. `factory script` and `factory review` use the same shared steps as the
  orchestrator, so they now reuse stored A3 and panel outputs unless `--fresh`.
- `scripts/ci.sh` passes from `docker compose down -v` in 22-25 s; 219 tests.

## Surprises
- The local Homebrew FFmpeg 9 has neither `drawtext` nor `subtitles`, so captions are drawn on the
  frames with Pillow and FFmpeg only encodes. This works on any FFmpeg build.
- Computed fields (`passed`, `total_usd`) are written into envelopes and rejected on load by
  `extra="forbid"`; `factory.artifacts.load` drops them.
- A crash after a vendor bills but before the job commits lost the spend. Now an artifact's cost is
  charged when the episode first points at it.
- Without a ruff config, `ruff check` picked up a user-level config (67 findings on clean main);
  `pyproject.toml` now pins line length 120 and the default rule set.
- The code review found: a gate-2 reject crashed the runner, two concurrent runs could upload twice,
  envelopes were not written atomically, the retry cap reset on every restart, the budget was not
  checked before a step, LLM ids were used as file names, and `decide` accepted a decision for a gate
  the episode was not at. All are fixed and tested
  (`plans/reports/code-reviewer-261022-2145-walking-skeleton-review.md`).

## Decision
- A gate-2 reject escalates the episode, because §5 defines no rewind for it.
- The episode budget comes from `spec.budget_usd`. The Channel Bible has no budget field, so the
  en config_hash is unchanged.

## Next steps
- Product decision: a panel or gate-1 reject goes back to DRAFTED, but nothing feeds the reviewer
  notes to A2 or A3, so the rewrite reuses the same script. Either feed the notes back or escalate
  directly.
- The artifact store root is not pinned per episode; resuming with a different `--artifacts` escalates.
- Low-severity review items are still open (see the report).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
