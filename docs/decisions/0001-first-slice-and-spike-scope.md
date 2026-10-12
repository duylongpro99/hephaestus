# ADR 0001: First slice and script spike scope

- **Date:** 2026-10-11
- **Status:** accepted
- **Decided by:** the user (project owner)
- **Context:** [architecture.md §19](../architecture.md) lists the decisions left open by the
  research. The EN A2 script spike (`plans/261011-0542-en-a2-script-spike/`) depends on four of
  them. This record fixes their values so that code and prompts read them from the repo.

## Decisions

| # | Decision | Value | Status |
|---|---|---|---|
| 1 | First slice | `en` × adult × CEFR A2 | decided |
| 2 | Support languages | `en` and `vi` | decided |
| 3 | Script review | two-persona agent panel | decided |
| 4 | Host voice | none chosen | deferred |
| 5 | Business model | none chosen | deferred |

### 1. First slice: `en` × adult × CEFR A2

The spike produces English scripts for adult learners at CEFR A2.

This differs from the ranking in [research.md §A.6](../research.md), which put JP-adult first and
EN-adult second. The user chose EN because the riskiest assumption, that an LLM can write at a
controlled level, is cheapest to test in English: spaCy and NGSL are mature, and the user can
judge the output directly. The factory design is language-agnostic, so this choice does not
change the architecture.

### 2. Support languages: `en` and `vi`

Every script carries two support-language layers:

- `en`: for an English target this is **not** a translation. It is a simple-English gloss of
  each vocabulary item, written within A2 vocabulary.
- `vi`: a full Vietnamese translation of every line and a Vietnamese gloss of every vocabulary
  item.

### 3. Script review: a two-persona agent panel

A native human reviewer is replaced, for the spike, by two independent reviewer agents with
opposite priorities:

- **Reviewer T, "Strict examiner":** a native English ESL teacher and examiner. Checks grammar,
  collocations, level fit, the target grammar point and the simple-English glosses.
- **Reviewer L, "Vietnamese A2 learner":** checks whether an A2 learner can follow each line,
  the accuracy and naturalness of the Vietnamese, and whether the episode is engaging.

Each reviewer runs as its own call. Neither sees the other's output or the Level Editor's
reasoning. Each returns a `QAReport` and a `GateDecision`; a `critical` issue forces a reject.

- **Known risk:** the reviewers come from the same model family as the writer, so they may share
  its blind spots. Small grammar slips and unnatural collocations are the most likely to pass.
- **Mitigation:** the user reads 2 of the 10 scripts (the panel's best and worst rated) and
  records a `GateDecision` with `user: human`.
- **Revisit trigger:** the panel and the user disagree on either spot-checked script. If that
  happens, the panel is not trusted as a gate and a human or cross-vendor reviewer is required
  before the walking skeleton.

### 4. Host voice: deferred

A script spike produces no audio. The choice is needed before TTS work begins.

### 5. Business model: deferred

It does not affect script quality. The choice is needed before publishing work begins.

### 6. Spike episodes: 10-15 second clips (2026-10-12)

To keep the spike short and cheap, each spec is a `micro_dialogue` clip of 0.17-0.25 minutes:
one dialogue of 2-4 lines, one target word, no explanation, replay or quiz. The channel's
`band_overrides` lower `target_repetition_min` to 1 and raise `new_word_max` to 0.10 so a
clip is not failed for its own target word. Sentence length is gated by its ceiling only.
Three specs are also drafted by `qwen3.8-max-0902` (`*-qwen`) to compare its Vietnamese with
DeepSeek's. A go result proves clip-level quality only; full 6-8 minute episodes need their own
run before production.

## Consequences

- `config/channels/en-podcast-spike.yaml` sets `target.pack: en`, `audience: adult`,
  `levels: [A2]` and `support_languages: [en, vi]`.
- The Scriptwriter prompt asks for a simple-English gloss and a Vietnamese gloss per vocabulary
  item, and a Vietnamese translation per line.
- The review panel lives in `factory/agents/review_panel/`.
