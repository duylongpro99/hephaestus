# EN A2 script spike: results and go/no-go

- **Date:** 2026-10-22
- **Plan:** `plans/261011-0542-en-a2-script-spike/`
- **Recommendation:** **Go**, with two quality fixes to carry into the next phase (gloss precision
  and dialogue coherence).

## What ran

Ten `micro_dialogue` clips of 10-15 seconds (ADR 0001, decision 6), one A2 target word each, en
× adult × A2 with `vi` support. The writer and the level editor ran on `ds/deepseek-v4-pro`. The
examiner reviewed on `kimi/kimi-k3` and the learner on `qwen3.8-max-0902`, all through AI Box
(ADR 0002). The final run is commit `963f0ce`. Data: `evals/en/adult/reviews/summary.json`.

A go result covers clips only. Full 6-8 minute episodes were not run.

## Results against the acceptance criteria

| Criterion | Result |
|---|---|
| All 10 scripts pass the code gates | Met: 10/10. Eight passed on the first draft; x06 and x08 failed `duration` and passed after one A3 turn. Coverage was 100% in every clip. |
| Each reviewer approves at least 8 of 10 | Met: the examiner approved 10/10 (2 approve, 8 edit-and-approve); the learner approved 10/10 (all edit-and-approve). |
| No critical issue | Met in the final run. The first run had one: x07's `birthday` gloss. |
| Spot-check comparison on 2 scripts | Done; see below. |

**Reviewer agreement:** both reviewers approved every clip, so they agree 10/10 on approve
versus reject. On approve versus edit-and-approve they agree on 8/10 (x02 and x07: the examiner
approved as-is, the learner asked for edits).

**Level fit:** the profiler passed every clip at A2, and both reviewers rated all 10 `at` the
level. Nothing in this run argues for changing the NGSL cutoffs.

## Main error classes (major issues, final run)

| Class | Count | Example |
|---|---|---|
| Gloss too loose | 5 | `motorbike`: "a bike that goes by itself"; `bus`: "a big car" |
| Dialogue does not hang together | 5 (consistency 3, comprehension 2) | x08: Anna asks about a vegetable, Ben answers that food is ready |
| Vietnamese sounds translated | 2 | x02: "làm ơn" at the end of a request |
| Other | 6 | engagement, collocation, a tense mismatch, one translation-accuracy issue |

The first prompt round fixed the other big class: Vietnamese that was too formal between friends
(`tôi`, `vâng`, `chúng ta`) fell from 6 clips to 0.

## Cost and time

| | Total for 10 | Per approved clip |
|---|---|---|
| Script (A2 + A3) | $0.043 | $0.004 |
| Panel (2 reviewers) | $0.174 | $0.017 |
| **All** | **$0.217** (about 5,600 VND) | **$0.022** |

A script took 61 s on average (86 s at most). Prices are AI Box internal dollars at 26,000 VND
each.

## Spot-check: panel versus user

| Clip | Why chosen | Examiner | Learner | User |
|---|---|---|---|---|
| x07 | Best: examiner approved as-is, gloss 5/5 | approve | edit-and-approve | approve |
| x08 | Worst: 5 major issues | edit-and-approve | edit-and-approve | approve |

Everyone approved both clips, so the ADR 0001 revisit trigger (panel and user disagree) did not
fire. The user approved all ten without line notes, so this comparison confirms the approve
decision but does not test whether the panel's major issues are real. That stays open.

## Changes made during the spike

Each change bumped the affected `station_version`.

1. Sentence length is gated by its ceiling only (natural dialogue averages about 5 words).
2. Episodes became 10-15 second clips. The channel lowers `target_repetition_min` to 1 and raises
   `new_word_max` to 0.10, since one target word is already 5-10% of a clip's lemmas.
3. The writer prompt gained rules for casual register between friends, glosses that define the
   word itself, using every review word, and showing the theme.
4. A Qwen writer was tried and dropped: its JSON-object output was structurally invalid on
   every attempt.

## Recommendation

**Go.** The pipeline writes level-correct A2 clips with good Vietnamese for about 2 US cents each,
and an independent panel approves them all. Two weaknesses must be fixed before content goes to
production, but neither blocks the next build phase:

- **Gloss precision:** a prompt rule improved the wording but not the accuracy. Add a gloss
  check, for example A3 or a small reviewer pass that compares each target gloss with
  WordNet's definition.
- **Dialogue coherence:** 2-4 line scenes often break their own logic. Ask the writer to plan
  the exchange (question, answer, reaction) before writing it, and have A3 check coherence.

## Open questions

- Should the gloss and coherence fixes come before the walking skeleton, or run alongside it?
- Do full 6-8 minute episodes need their own spike before production, as ADR 0001 decision 6
  says?

## Follow-up run: gloss and coherence fixes (2026-10-22)

The writer now gets the top three WordNet senses of each target and review word, and the clip
format asks for a planned exchange (opening, a reply that answers it, an optional reaction).

| | Before | After |
|---|---|---|
| Major or critical issues | 18 | 9 |
| Dialogue coherence (consistency, comprehension) | 5 | 0 |
| Loose glosses | 5 | 3 (2 of them review words: `bus`, `work`) |
| Examiner approvals | 10/10 | 9/10 |
| Learner approvals | 10/10 | 10/10 |
| Cost for 10 clips, script + panel | $0.22 | $0.22 |

The one reject is x09: its grammar note calls "every morning" an adverb of frequency, which the
examiner rated critical. Grammar notes are a new error class, not a regression of the fixes.
The learner reviewer (Qwen) once returned the decision `request_changes`, failed validation
after the repair round, and passed on a rerun.
