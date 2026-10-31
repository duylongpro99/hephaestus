# Code Review: walking skeleton (uncommitted)

## Scope
- Files: factory/orchestrator/{states,runner,repo,db,stations}.py, migrations/0001_init.sql, factory/workers/*.py, factory/adapters/{ffmpeg.py,tts,image,publish,llm/fake.py}, factory/artifacts.py, factory/cli.py, factory/config.py, scripts/ci.sh, compose.yaml, tests/test_{runner,e2e,state_machine,workers}.py
- Verification run: `uv run --offline pytest -q` with the db container up: 213 passed in 12s. Gate-2 reject probed directly (see H1).
- Plan: plans/261022-1420-walking-skeleton/plan.md, phase-04 and phase-05.

## Overall assessment
The core invariants mostly hold. The job row, artifact rows, cost rows and state move happen in one transaction (runner.py:137-150). Each artifact's cost is charged once, through `ON CONFLICT DO NOTHING` + rowcount. The C10 receipt is committed before the c10_upload artifact. Gate decisions are filtered by `status_changed_at` and by the panel personas. Autocommit plus `conn.transaction()` is correct psycopg3 usage. Four defects should still be fixed before this is called done: a gate-2 reject crashes the runner, the reject/rewrite loop is a no-op, there is no per-episode lock so C10 can upload twice, and a torn artifact write blocks the episode for good.

## High

### H1. Rejecting at gate 2 crashes `factory run`, and every later run crashes too
- states.py:55 has `gate_2` with no `on_reject`. states.py:109-110 raises `IllegalTransition`. runner.py:111-113 calls `after_attempt(state, "reject", ...)` without guarding it. cli.py:222-224 accepts `--gate 2 --decision reject`.
- Scenario: `factory decide spec --gate 2 --decision reject` prints "recorded ... `factory run` continues it". The next `factory run` dies with a traceback (`IllegalTransition: gate_2 cannot reject`, confirmed by calling `after_attempt(State.COMPLIANT, "reject", 1, 0)`). The reject row stays the latest decision since the gate was reached, so every later run crashes the same way until someone records an approve.
- Fix: decide what a final reject means. Either give gate 2 a destination (`on_reject=State.CANCELLED`, or ESCALATED for human triage), or have `_pass_gate` map a gate-2 reject to `escalate`. Also make `decide` refuse decisions the state machine cannot honour. Add a runner test for a gate-2 reject.

### H2. "Send back to DRAFTED" never rewrites anything: a panel reject always escalates and a human gate-1 reject has no effect
- states.py:47-48 (`on_reject=State.DRAFTED`). stations.py:79-97: the A3 inputs are `[draft, spec, config_hash, wordlist_hash]` with no reject feedback. stations.py:110: the panel inputs are `[spec, script]`.
- Scenario: the panel rejects and the episode goes back to DRAFTED. A3 has identical inputs, so it reuses the stored script (content addressing). The panel has identical inputs, so it reuses the stored reject. `rejects >= MAX_REJECTS` then sends the episode to ESCALATED. The "rewrite once" in phase-05 ("a critical issue sends the episode back to DRAFTED once, then escalates") is therefore a guaranteed escalation after a dead loop.
- For a human gate-1 reject, the same reuse returns the identical script to QA_OK and the human must reject again, forever. The reject `notes` never reach A2 or A3. tests/test_runner.py:128 asserts this behaviour (`builds["a3_level_editor"] == 1`), so the test locks in the bug instead of catching it.
- Fix: feed the rejecting decisions (notes, QAReport issues) into the A3 (or A2) inputs and prompt, so a rewind changes the inputs hash and runs a real rewrite. If that is deliberately deferred, make a reject escalate directly and document it. Do not loop through reused outputs that cannot change. Update the test to assert the rewrite received the feedback.

### H3. No per-episode lock: two concurrent `factory run` calls run every station twice and can upload twice
- runner.py:84-98 has no lock. stations.py:259-263 does read-then-upload. repo.move (repo.py:52-60) only detects the race after the station has already run.
- Scenario: a cron `factory run` and a manual run (or two shells) on the same FINAL_APPROVED episode. Both call `get_receipt`, both get None, both call `publisher.upload`. The second `insert_receipt` then hits the UNIQUE(episode, platform) violation, but the vendor upload has already happened twice. That breaks the "C10 never uploads twice" invariant. Earlier stations pay the LLM twice, and the loser crashes with a `RuntimeError` from `move`.
- Fix: take `pg_advisory_lock(hashtext(episode_id))`, or `SELECT ... FOR UPDATE NOWAIT` on the episode row with a session-level advisory lock, at the start of `advance` and hold it for the whole run. Refuse with a clear message if another runner holds it.

### H4. A torn artifact envelope blocks the episode permanently
- artifacts.py:99 (`path.write_text`, not atomic) and artifacts.py:121 (`path.exists()` treated as "done").
- Scenario: the process is killed (or the disk fills) while an envelope is being written. On resume `produce` sees the file, `json.loads` raises, the runner retries 3 times against the same corrupt file, and the episode goes to ESCALATED. Every retry fails the same way until someone deletes the file by hand. That breaks the "content addressing makes resume free" claim, which the crash test only covers at the station boundary, not mid-write.
- Fix: write to `path.with_suffix(".json.tmp")`, fsync, then `os.replace(tmp, path)`. Optionally treat an unreadable envelope as absent and rebuild it.

## Medium

### M1. `edit-and-approve` is treated as plain approve, so the edits are silently dropped
- runner.py:111 (`"reject" if ... else "ok"`). cli.py:211-228 has no `--diff` option, and `GateDecision.diff` is never applied.
- Scenario: a human records edit-and-approve believing their edits ship. The episode moves to SCRIPT_APPROVED and voices the unedited A3 script.
- Fix: until edit application exists, have `decide` and the runner reject `edit-and-approve` with a clear message. Alternatively, store the edited Script as a new `a3_level_editor` artifact in the same transaction as the move.

### M2. `factory decide` reports success for decisions the runner will ignore
- cli.py:238-244.
- Scenario: the episode is at ENRICHED (the runner crashed) or at QA_OK while the user passes `--gate 2`. The decision is written with `ts < status_changed_at` of the gate state, so `gate_decision_since` never sees it, yet the CLI prints "`factory run` continues it". The run then waits at the gate with no explanation.
- Fix: in `decide`, require `episode.status == GATES[gate]` (states.py:61) and otherwise print the current state and exit non-zero.

### M3. LLM-written ids become file paths and FFmpeg concat lines
- voice.py:67 (`lines_dir / f"{d.line_id}.wav"`), visuals.py:24 (`f"{segment.id}.png"`), render.py:53 and render.py:59 (`file '{...}'`). Script ids are unconstrained `str` (contracts/script.py:11 and :35).
- Scenario: A2 is a real LLM. An id such as `l1/../../x` writes outside the artifact media directory, and an id containing `'` breaks the concat playlist. The render then fails 3 times and the episode escalates.
- Fix: add an id pattern to the Script contract (`^[A-Za-z0-9_-]{1,64}$`, also enforced by A2/A3 validation), or name media files by index (`{n:04d}.wav`) and keep the id only in the manifest.

### M4. `factory script --max-turns` is not part of the A3 inputs, so changing it reuses the old result
- stations.py:83 (`inputs = [draft, spec, config.config_hash, wordlist_hash(...)]`, while `max_turns` changes behaviour). cli.py:117.
- Scenario: A3 escalated after 4 turns. The user reruns with `--max-turns 8` and gets the stored 4-turn ESCALATED result. This regression comes from the new "reuse a stored A3 unless --fresh" behaviour.
- Fix: add `max_turns` to the inputs list.

### M5. The retry cap is counted per `advance()` call, not per station
- runner.py:125 (`itertools.count(1)` compared with `max_attempts`). `earlier` is only used for numbering.
- Scenario: a station fails twice, and then the process is killed during the backoff sleep (Ctrl-C, deploy, OOM). The next run gets 3 fresh attempts. Repeated restarts never escalate, and each one pays for vendor calls.
- Fix: count the `retrying` jobs since the episode last entered `state` (job rows with `from_status = state` and `finished_at >= status_changed_at`) and start `attempt` from there.

### M6. The budget is checked only after a step, in a separate transaction
- runner.py:152 and runner.py:156-166.
- Scenario: a crash between the step's commit and the budget move resumes an over-budget episode in its next state, which runs a station and spends more before it is stopped. Unpriced entries (`priced=False`, usd 0) are also invisible to the budget.
- Fix: call `_stop_if_over_budget` at the top of the `advance` loop as well (cheap).

### M7. The artifact store root is not pinned to the episode
- cli.py:255 and cli.py:274 (`--artifacts`). runner.py:62-66 resolves relative URIs against whatever root the current run uses.
- Scenario: the episode is started with `--artifacts /tmp/x` and resumed without it (or the other way round). `latest_artifact` rows exist, but `store.read` raises FileNotFoundError, which is retried 3 times and then escalates.
- Fix: store the root (or a store id) on the episode at creation and refuse a mismatched `--artifacts`.

## Low

- L1. `latest_artifact` can return a stale pointer (repo.py:86 and repo.py:95). If the outputs go A, then B, then A again (for example a code change rolled back), the re-pointing to A is a no-op insert, so `ORDER BY id DESC` still returns B. Content addressing explicitly promises that rolling back finds the old output. Fix: on conflict, update a `pointed_at` column and order by that.
- L2. Naive and past publish times (episode_spec.py:34, publisher.py:28-32). A `publish_slot` without an offset is accepted and stored by Postgres using the session TZ (UTC), not the channel's timezone (`channel.timezone` is never populated). A slot that passes while the episode waits at gate 2 is scheduled in the past. Fix: use `AwareDatetime` and reject or escalate past slots in `c10_schedule`.
- L3. `repo.schedule_receipt` (stations.py:275) commits outside the job transaction, so a receipt can read `scheduled` while the job failed. This is harmless while scheduling is idempotent, but it should go into the runner transaction or be documented.
- L4. A C10 vendor upload that succeeds followed by a failed `insert_receipt` (DB blip) still uploads again on retry (stations.py:260-263). This is inherent without a vendor idempotency key. Record it as a known risk for the real YouTube adapter (store an "upload started" marker or use a client-generated idempotency token).
- L5. Panel decisions are inserted into `gate_decision` again on every panel pass, including reused ones with their old timestamps (runner.py:144-145). This is harmless today because of `panel_users`, but `Runner(panel_users=())` is the default. A caller that forgets it relies only on the timestamp filter. Make the persona exclusion intrinsic (for example, only `user = 'human'` or `'auto'` opens a gate).
- L6. scripts/ci.sh: `$ARTIFACTS` and the `factory_ci` database are left behind on failure. Add `rm -rf` to the trap if that matters for hosted runners.

## Edge cases checked and holding
- Cost charged once: verified for reuse (`insert_artifact` rowcount) and for crash-then-resume (tests/test_runner.py:158-180).
- Gate timing filter and panel exclusion: correct as written. A stale reject at QA_OK is ignored after the rewind.
- The receipt is committed before the c10_upload artifact and job. A rerun from FINAL_APPROVED does not upload (tests/test_e2e.py:62).
- Migrations are idempotent per file, inside a transaction. `ci.sh` checks the second migrate is a no-op.

## Plan follow-ups
- Success criteria appear met for migrate, the unit state-machine tests, xx-fixture conformance, the e2e run to SCHEDULED, C9, the no-double-upload-on-rerun case, the gate wait and resume, and ci.sh.
- Not met in substance: phase-05 "panel reject sends the episode back to DRAFTED once" (H2). The "receipt check holds" claim holds only for sequential reruns (H3).

## Unresolved questions
- Should a gate-2 reject cancel the episode, escalate it, or rewind to a specific station?
- Is a feedback-driven rewrite in scope for the skeleton, or should a reject escalate directly until A3 accepts reviewer notes?

Status: DONE_WITH_CONCERNS
Summary: The core transactional, cost and receipt invariants hold and all 213 tests pass. Gate-2 reject crashes the runner, the reject/rewrite loop is a no-op, there is no per-episode lock so C10 can upload twice, and a torn envelope write blocks an episode permanently.
Concerns/Blockers: H1-H4 should be fixed before marking the plan complete; H2 needs a product decision on what a reject means.
