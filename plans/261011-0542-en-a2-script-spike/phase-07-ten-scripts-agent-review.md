---
phase: 7
title: "10 scripts and two-persona review panel"
status: pending
priority: P1
effort: "2d"
dependencies: [6]
---

# Phase 7: 10 scripts and two-persona review panel

## Goal
Generate all 10 scripts and have two independent reviewer agents judge each one from opposite viewpoints. Then write a go/no-go report that decides whether to build the walking skeleton next.

## Reviewer personas

| | **Reviewer T: "Strict examiner"** | **Reviewer L: "Vietnamese A2 learner"** |
|---|---|---|
| Who | A native English ESL teacher and Cambridge-style examiner who is picky about accuracy | A 28-year-old Vietnamese office worker at A2 who listens on the commute |
| Checks | Grammar errors, unnatural collocations, grammar above A2, a wrong or missing target grammar point, an inaccurate simple-English gloss | Whether they can follow each line, accuracy and naturalness of the `vi` translation, whether the hook makes them keep listening, boring or confusing segments |
| Bias it counters | It counters the learner's leniency on correctness. | It counters the examiner's indifference to engagement and to the Vietnamese text. |

The same rules apply to both reviewers:
- Each one makes its own call and never sees the other reviewer's output or A3's reasoning.
- Each one returns a `QAReport` and a `GateDecision`. A `critical` issue forces a reject.

## Files to Create / Modify
- Create: `factory/agents/review_panel/persona_examiner.md`
- Create: `factory/agents/review_panel/persona_learner.md`
- Create: `factory/agents/review_panel/agent.py`: runs both personas on one script and returns two `QAReport`s and two `GateDecision`s.
- Create: `tests/test_review_panel.py`: tests parsing and the decision rules, such as "critical forces reject", against recorded fixture responses. No network calls.
- Create: `evals/en/adult/reviews/`: panel outputs for each script, plus the user's spot-check `GateDecision`s.
- Create: `plans/reports/spike-261011-en-a2-script-results.md`

## Tasks & Steps
1. Run `factory script` on all 10 specs. For each one, record the gate status, the number of A3 turns, the USD cost and the run time.
2. Run the panel on every script that passes the gates. Add the panel's cost to each script's ledger.
3. Fix prompt or profiler issues and re-run. Each change bumps `station_version`, and the report records it.
4. **User spot-check:** the user reads 2 scripts, one the panel rated best and one it rated worst. The user records a `GateDecision` (user `human`) for each, using the same rubric.
5. Write the report. It covers:
   - the pass rate at each gate;
   - the approval rate from each reviewer, and how often the two agree;
   - the main error classes;
   - the cost per approved script;
   - the profiler's level verdict compared with Reviewer T's level-fit verdict, which calibrates the cutoffs;
   - the panel's verdicts compared with the user's on the 2 spot-checked scripts;
   - a go or no-go recommendation.
6. Approved scripts become the first golden evals for `en` × adult.

## Verification
- `uv run pytest tests/test_review_panel.py` passes.
- All 10 scripts pass the code gates.
- Both reviewers approve at least 8 of the 10, and neither reports a critical issue.
- The report states go or no-go with evidence and includes the spot-check comparison.
