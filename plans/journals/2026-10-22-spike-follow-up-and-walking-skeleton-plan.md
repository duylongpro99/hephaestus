---
title: Spike follow-up and walking skeleton plan
date: 2026-10-22
summary: Dictionary senses and a planned exchange halved panel issues; walking skeleton planned on Postgres and FFmpeg
---

# Spike follow-up and walking skeleton plan

## What happened
- The EN A2 clip spike ended in go (`plans/reports/spike-261011-en-a2-script-results.md`).
- Follow-up fix: the writer now gets the top three WordNet senses per target and review word
  (`dictionary_senses` on the pack protocol), and the micro_dialogue format asks for a planned
  exchange. Panel major or critical issues fell from 18 to 9, coherence issues from 5 to 0,
  loose glosses from 5 to 3. Commit `47010e7`.
- New error class: wrong grammar notes (x09 rejected for calling "every morning" an adverb of
  frequency).
- The Qwen learner reviewer once returned `request_changes`, failed validation after the repair
  round, and passed on rerun. Batch helper scripts in the session scratchpad vanished between
  sessions, so the first rerun silently did nothing.

## Decision
- Walking skeleton plan: `plans/261022-1420-walking-skeleton/` (commit `0b75686`). Postgres via
  Docker Compose, FFmpeg placeholder MP4, SPEC to SCHEDULED with auto-approved gates in e2e,
  synchronous in-process runner. Local `scripts/ci.sh` stands in for CI (no git remote).

## Next steps
- `/ak:cook plans/261022-1420-walking-skeleton/plan.md`.
- Later: a grammar-note check, and a 6-8 minute episode spike before production.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
