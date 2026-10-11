---
title: "EN A2 script spike"
description: "Prove that an LLM can write CEFR A2 English podcast scripts that pass code-based lexical gates and an independent two-persona review panel, using the real contracts and en pack layout."
status: pending
priority: P1
effort: 9d
tags: [feature, backend, experimental]
blockedBy: []
blocks: []
created: 2026-10-11
---

# EN A2 script spike

## Overview

The spike tests the riskiest assumption behind the factory: that A2 (Scriptwriter) and A3 (Level Editor) can produce scripts at the right level. If they cannot, nothing else in `ARCHITECTURE.md` is worth building.

The code will not be thrown away. It implements part of §17 step 1 (contracts, the `en` Language Pack, the profiler, A2 and the A3 loop) and follows the §15 repository layout. It also builds a two-persona review panel, which is an early form of the A4/A5 judges.

## Brainstorm contract

- **Outcome:** about 10 EN A2 adult podcast scripts that pass the code gates and are approved by the review panel, plus a go/no-go report.
- **Constraints:**
  - Only commercially licensed data is ingested: NGSL 1.2 and NGSL-Spoken (CC BY-SA), and Open English WordNet (CC BY 4.0).
  - EVP, Oxford 3000 and CEFR-J are never ingested. EVP may be used only for a manual spot-check of the band cutoff.
  - The Python layout and contracts follow `ARCHITECTURE.md` §4 and §15.
  - The YPP threshold rises on 2027-02-01, so the spike must finish in about two weeks.
- **Non-goals:**
  - TTS, rendering, captions, thumbnails, the console and publishing.
  - The orchestrator state machine, Postgres and the walking skeleton.
  - A1 Showrunner and the originality gate.
  - The `ja` pack.
- **Acceptance criteria:** see Success Criteria.

## Decisions (user, 2026-10-11)

| Decision | Value |
|---|---|
| First slice | `en` × adult × CEFR A2 |
| Support languages | `en` and `vi`. For an English target, `en` means a simple-English gloss and `vi` means a full translation. |
| Reviewer | Two independent reviewer agents with different personas replace the native human reviewer. |
| Host voice, business model | Deferred. Neither affects a script spike. |

## Trade-offs

- **Panel instead of a human:** this is fast and free of hiring. It assumes that two persona prompts catch different errors. It fails first if the panel shares the writer's blind spots, because Claude would be judging Claude. A1-level grammar slips and unnatural collocations are the most likely to get through. The mitigation is that the user reads 2 of the 10 scripts, so that the report can compare the panel's verdict against a human one (phase 7). The user decided this; the risk is recorded here and not reversed.
- **NGSL rank as a proxy for A2:** NGSL has no CEFR tags. The A1 and A2 cutoffs are rank thresholds (research.md §A.2 rule 3, marked [P]). They are calibrated in phase 4 against a manual EVP spot-check.

## Phases

| # | Phase | Effort | Depends on | Status |
|---|---|---|---|---|
| 1 | [Repo setup](./phase-01-repo-setup.md) | 1h | none | Pending |
| 2 | [Decisions record](./phase-02-decisions-record.md) | 0.5d | 1 | Pending |
| 3 | [Contracts and config layers](./phase-03-contracts-and-config.md) | 1d | 1 | Pending |
| 4 | [en pack and wordlist ingestion](./phase-04-en-pack-wordlist-ingestion.md) | 1.5d | 3 | Pending |
| 5 | [Lexical profiler](./phase-05-lexical-profiler.md) | 1.5d | 4 | Pending |
| 6 | [Specs, A2 Scriptwriter and A3 loop CLI](./phase-06-a2-a3-script-cli.md) | 2.5d | 2, 5 | Pending |
| 7 | [10 scripts and two-persona review panel](./phase-07-ten-scripts-agent-review.md) | 2d | 6 | Pending |

## Success Criteria

- [ ] `uv run pytest` passes: contract tests, `en` pack conformance tests, profiler tests and panel parsing tests.
- [ ] 10 Episode Specs exist under `evals/en/adult/specs/` and validate.
- [ ] All 10 scripts pass the code gates within 4 A3 turns:
  - at least 95% of tokens are at A2 or below;
  - each target word appears at least 5 times;
  - sentence length is within the A2 band;
  - estimated duration at 100–120 wpm is within the spec length.
- [ ] Both panel reviewers approve at least 8 of the 10 scripts, either outright or after minor edits, and neither reports a critical issue.
- [ ] Cost per script, A3 turns and panel cost are recorded.
- [ ] A go/no-go report exists in `plans/reports/`. It includes the panel-versus-user comparison on 2 scripts.

## Risks

| Risk | Mitigation |
|---|---|
| The panel shares the writer's bias, so the approval rate is inflated | Independent calls; personas with opposite priorities; the panel never sees A3's reasoning; user spot-check on 2 scripts |
| The NGSL rank cutoff misjudges A2 | Calibrate in phase 4; the report compares the profiler's verdict with the panel's level-fit verdict |
| The Vietnamese translation is wrong | The learner persona reviews it specifically; the user can verify it as a native speaker |
| Model IDs or SDK APIs have changed since ARCHITECTURE.md was written | Load the `claude-api` skill before writing the phase 6 code |
