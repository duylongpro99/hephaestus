# Code review: EN A2 script spike

- **Range:** commits 7cb4714..7ccd016, with fixes in 056c94d.
- **Reviewer:** a code-reviewer subagent.
- **Verdict before fixes:** not ready for the 10-spec run.
- **After fixes:** all 67 tests pass, and every finding except two is fixed. M6 was rejected on evidence and M4 needs the user's decision on a threshold.

## Findings and resolution

| # | Severity | Finding | Resolution |
|---|---|---|---|
| H1 | high | A typographic apostrophe (’) turned `n’t` and `’s` into off-level tokens that A3 could not fix | Fixed. `EnPack.tokenize` normalizes ’ and ‘ before spaCy runs; a test checks that curly and straight apostrophes give the same report. |
| H2 | high | Off-level words in quiz items failed the gate, but A3 had no tool to edit quiz items | Fixed. A3 has a new `edit_quiz_item` tool, and the flagged-line text now covers quiz items. |
| H3 | high | Dialogue-to-replay syncing worked in one direction only and broke after a direct replay edit or a delete | Fixed. Replay ids are rejected with the dialogue id to edit instead. Every dialogue edit rebuilds the replay, A3 has a `sync_replay` tool, and a new `replay_mismatch` gate catches drift (LevelReport schema 1.1.0). |
| H4 | high | With server-side fallback, cost was priced from the top-level usage only, and an unknown model raised after a paid call | Fixed. Each billed attempt in `usage.iterations` is priced separately. An unknown model is recorded with `priced: false` and no exception (CostLedger schema 1.1.0). |
| M1 | medium | The SDK parsed the stream before `check_stop`, so a truncated response or fallback raised `ValidationError` | Fixed. The call uses `output_config.format` with `transform_schema` and parses the text after the last `fallback` block, only once `check_stop` has passed. |
| M2 | medium | Costs were lost when an A2 or A3 call raised | Fixed. `LLMError.costs` carries the billed entries, and `level_loop` catches the error and stops with `ESCALATED` plus the error message. |
| M3 | medium | The A2 cache key left out the level wordlist and the client code | Fixed. The wordlist hash is part of the A2 and A3 inputs, and `anthropic_client.py` is part of the A2 `station_version`. |
| M4 | medium | The few-shot example failed its own gates | Partly fixed. The replay is now complete and the example has no off-level words. Its mean sentence length is still 6.85, below the A2 band's lower bound of 8; that waits on the sentence-length decision. |
| M5 | medium | Inflected target forms (`renting`) and multi-word targets were not counted | Fixed. Targets match their lexicon forms, and multi-word targets are counted as phrases. |
| M6 | medium | Sonnet 5.5 cache-read price should be 0.10 | Rejected. The bundled `claude-api` reference (cached 2026-10-06) says "cache reads $0.20" for Claude Sonnet 5.5. The spike does not use that model. |
| L1 | low | Clitics counted as content tokens | Fixed. Content tokens must be words, so clitics are excluded. |
| L2 | low | Interjections such as `um` counted as off-level | Fixed. INTJ tokens are left out of coverage. |
| L3 | low | Panel cost was not in the script ledger, and `hard_gate_failures` / level fit were not acted on | Panel cost now goes into the episode's ledger. Level fit is recorded for the report's comparison. `hard_gate_failures` stays advisory, because the personas define no hard gates. |
| L4 | low | Speaker not checked; A3 output not re-validated | Fixed. The speaker must be in the cast, and the script is re-validated after each A3 turn. |
| L5 | low | An invalid `--decision` gave a traceback | Fixed. It now raises `BadParameter`. |
| L6 | low | A re-run overwrote the previous run record | Fixed. `runs/{episode}.json` keeps every attempt, and the summary reads the latest one. |

## Open questions from the review

- Should on-screen quiz text be held to the ≥98% coverage rule? For now it is counted in the 95% spoken coverage; a separate on-screen gate is not built.
- Should a target word already at or below the level count as a new word? For now yes: a target word is new by definition of the spec.
