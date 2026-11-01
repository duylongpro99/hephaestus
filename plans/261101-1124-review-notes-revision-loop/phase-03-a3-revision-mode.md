---
phase: 3
title: "A3 chế độ sửa theo ghi chú và nối vào station"
status: completed
effort: 2.5h
---

# Phase 3: A3 chế độ sửa theo ghi chú

## Context

- `factory/agents/a3_level_editor/agent.py`: `level_loop` chỉ chạy turn khi level gate fail;
  `build_user` chỉ đưa gate report, spec và script.
- `factory/agents/a3_level_editor/prompt.md`: prompt chỉ nói về sửa level gate.
- `factory/orchestrator/stations.py`: `Stations.level_editor` luôn đọc draft của A2;
  `level_script` hash input `[draft, spec, config_hash, wordlist_hash, max_turns]`.
- Envelope của mỗi persona panel (`review_<persona>`) có `extra["gate_decision"]`; QAReport của persona
  đọc bằng `ctx.read(panel.station(p), QAReport)`.
- Gate 1 của người duyệt là row `gate_decision` (gate 1, `decision = 'reject'`, user không thuộc
  `panel.PERSONAS`).

## Yêu cầu

1. `level_loop(..., revision: RevisionRequest | None = None)`:
   - Khi có `revision`, chạy ít nhất một turn kể cả khi level gate đã pass; các turn sau chỉ chạy khi
     level gate fail (như hiện nay), tối đa `max_turns`.
   - `build_user` thêm khối "Reviewer feedback" liệt kê notes và issues (line_id, severity,
     description, suggested_fix) khi có `revision`. Ghi chú đi nguyên văn; không rẽ nhánh theo ngôn ngữ.
   - Nếu có `revision` mà script sau loop giống hệt script vào (so bằng hash/`model_dump`), trả
     `status = "ESCALATED"` với error rõ ràng ("revision made no changes").
2. `prompt.md`: thêm mục "Revising after review": sửa đúng những gì reviewer nêu, giữ phần còn lại,
   sau đó vẫn phải pass level gate; dùng cùng bộ tool. Prompt bằng tiếng Anh.
3. `level_script(..., revision: RevisionRequest | None = None)`: khi có `revision`, thêm nó vào input
   của cả `a3_level_editor` lẫn `level_report`. Khi `None` thì list input giữ nguyên như cũ, để lệnh
   `factory script` và `factory review` không đổi hành vi.
4. `Stations.level_editor`:
   - `rewrites = repo.count_rewrites(ctx.conn, ctx.episode)`.
   - `rewrites == 0`: như hiện nay (draft của A2).
   - `rewrites > 0`: đọc script A3 mới nhất (`ctx.read(a3.STATION, Script)`), dựng `RevisionRequest`
     từ lần reject gần nhất, produce nó thành artifact `revision_request` (station version `CODE`,
     input là ghi chú và script bị reject), rồi gọi `level_script(ctx, rejected_script, …, revision=req)`.
   - Lần reject gần nhất: job `rejected` → `DRAFTED` cuối cùng (thêm `repo.last_rewrite_job` hoặc trả
     kèm trong `count_rewrites`). Nếu station là `review_panel`: mỗi persona có
     `gate_decision.decision == "reject"` thành một `ReviewerNote` với `issues` từ QAReport của persona.
     Nếu là `gate_1`: lấy row `gate_decision` gate 1, `reject`, mới nhất, user không thuộc
     `panel.PERSONAS` (thêm hàm repo nếu `gate_decision_since` không đủ).
   - `RevisionRequest` không hợp lệ (không có ghi chú) → `StationResult("escalate", ...)`.
5. `factory decide`: `--decision reject` bắt buộc `--notes` không rỗng (`typer.BadParameter`).
6. Kiểm lại các station sau (`enrich`, `review_panel`, `voice_lines`, …): chúng đọc
   `ctx.read(a3.STATION, Script)` = artifact mới nhất, nên tự dùng script đã sửa. `review_script` hash
   theo script, nên panel chấm lại thật.

## Files

- Sửa `factory/agents/a3_level_editor/agent.py`, `factory/agents/a3_level_editor/prompt.md`.
- Sửa `factory/orchestrator/stations.py`, `factory/orchestrator/repo.py`.
- Sửa `factory/cli.py` (lệnh `decide`).
- Sửa `tests/test_script_steps.py`, `tests/test_runner.py`; có thể thêm `tests/test_revision.py`
  cho unit test của A3 với `FakeLLMProvider`.

## Test

- Unit, không DB (`FakeLLMProvider` với fixture tool loop trong `tmp_path`):
  - script pass level gate + `revision` → A3 chạy đúng 1 turn, tool `edit_line` được gọi, script đổi;
  - `user` gửi cho LLM có khối "Reviewer feedback" chứa notes và `line_id` của issue;
  - fixture không gọi tool nào → `ESCALATED` với lý do "no changes";
  - `revision=None` → hành vi cũ (0 turn khi pass), hash input không đổi so với trước.
- `level_script` với cùng `revision` hai lần → lần hai `reused` (idempotent).
- Runner với station thật cần LLM nên để phase 4. Ở phase này cập nhật test toy trong
  `tests/test_runner.py` nếu phase 1 chưa làm.
- CLI: `factory decide --decision reject` không notes → exit code khác 0.
- Lệnh: `uv run pytest tests/test_script_steps.py tests/test_revision.py`, rồi
  `uv run pytest -m "not db and not e2e"`.

## Rủi ro và rollback

- `a3.version` đổi → cache A3 cũ không dùng được nữa (đã ghi ở plan).
- A3 có thể sửa dòng dialogue mà quên replay; `_after_change` và `sync_replay` hiện có đã xử lý,
  level gate `replay_mismatch` sẽ bắt nếu sót.
- Rollback: revert các file trên; contract ở phase 2 có thể giữ lại.
