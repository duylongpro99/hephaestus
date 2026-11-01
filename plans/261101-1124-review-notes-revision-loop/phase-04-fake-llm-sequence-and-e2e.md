---
phase: 4
title: "Fake LLM theo lượt gọi, fixture và test end-to-end"
status: completed
effort: 1.5h
---

# Phase 4: Fake LLM theo lượt gọi và test end-to-end

## Context

- `factory/adapters/llm/fake.py`: mỗi station chỉ có một `{station}.json`, nên panel không thể
  "reject rồi approve" và A3 không thể sửa khác nhau qua hai vòng.
- `factory run --fake-llm` đọc fixture từ `tests/fixtures/<pack>/<episode_id>/` (`factory/cli.py`).
- Spec CI: `evals/xx-fixture/adult/specs/xx-A2-e2e.json`; fixture: `tests/fixtures/xx-fixture/xx-A2-e2e/`.
- Fixture panel có sẵn ở `tests/fixtures/panel/` (`learner_critical.json` là một verdict reject).

## Yêu cầu

1. `FakeLLMProvider` hỗ trợ fixture theo lượt gọi: lần gọi thứ n cho station dùng
   `{station}.{n}.json` nếu có, nếu không thì `{station}.json`. Bộ đếm theo instance (trong một
   process). Cập nhật docstring nói rõ giới hạn này. `identity` vẫn hash mọi `*.json` nên không đổi
   cách tính.
2. Hai episode fixture mới trên pack `xx-fixture` (copy từ `xx-A2-e2e`, đổi `episode_id`):
   - `xx-A2-revise`: `review_examiner.1.json` reject (issue có `line_id` và `suggested_fix`),
     `review_examiner.2.json` approve; `a3_level_editor.json` gọi `edit_line` trên dòng đó.
   - `xx-A2-revise-cap`: panel luôn reject; `a3_level_editor.1.json` và `.2.json` sửa hai dòng khác
     nhau, để vòng thứ hai cũng đổi script và lần escalate là do hết vòng chứ không do "no changes".
3. Spec tương ứng đặt cạnh spec e2e trong `evals/xx-fixture/adult/specs/`.

## Files

- Sửa `factory/adapters/llm/fake.py`, `tests/test_fake_llm.py`.
- Tạo `tests/fixtures/xx-fixture/xx-A2-revise/*.json`, `tests/fixtures/xx-fixture/xx-A2-revise-cap/*.json`.
- Tạo `evals/xx-fixture/adult/specs/xx-A2-revise.json`, `evals/xx-fixture/adult/specs/xx-A2-revise-cap.json`.
- Tạo `tests/test_revision_e2e.py` (marker `e2e` và `db` như `tests/test_e2e.py`, dùng chung fixture
  DB và cách gọi CLI ở đó).

## Test

- `tests/test_fake_llm.py`: `{station}.1.json`, `{station}.2.json` được dùng theo thứ tự, lần thứ ba
  về `{station}.json`; thiếu cả hai thì lỗi như cũ.
- `tests/test_revision_e2e.py` (`--fake-llm --auto-approve`, profile media `fake`):
  - **reject rồi viết lại khác đi**: `xx-A2-revise` tới `SCHEDULED`; có 2 artifact `a3_level_editor`
    với hash khác nhau; có 1 artifact `revision_request` với notes của examiner; job
    `review_panel` là `[rejected, succeeded]`; dòng bị sửa trong script cuối có text mới.
  - **quá số vòng thì ESCALATED**: `xx-A2-revise-cap` dừng ở `ESCALATED`; job `review_panel` là
    `[rejected, rejected, escalated]`; job cuối có error nói hết vòng sửa; có đúng 2 artifact
    `revision_request` (round 1 và 2).
  - **reject ở gate 1 bởi người** (không `--auto-approve`): chạy `xx-A2-revise` với panel approve
    (fixture riêng hoặc dùng `.2.json` qua thứ tự), dừng ở `QA_OK`; `factory decide --decision reject
    --notes "..."`; `factory run` lần nữa cho ra script A3 mới và dừng lại ở `QA_OK`;
    `revision_request` có `rejected_by = "gate_1"` và notes của người. Nếu bộ đếm theo process làm
    fixture khó sắp, test này có thể gọi `Runner` trực tiếp thay vì CLI.
- Lệnh: `uv run pytest tests/test_fake_llm.py`, `uv run pytest tests/test_revision_e2e.py`
  (cần `DATABASE_URL`, `ffmpeg`), rồi `uv run ruff check . && uv run pytest` và `scripts/ci.sh`.

## Rủi ro và rollback

- Bộ đếm theo process không đúng qua nhiều lần `factory run`; chỉ dùng cho test, đã ghi trong docstring.
- Episode `xx-A2-revise` chạy full pipeline nên test chậm hơn; nếu quá chậm, test "quá số vòng" đủ
  dùng vì dừng sớm ở `ESCALATED`.
