---
phase: 1
title: "Giới hạn vòng sửa chung trong state machine"
status: completed
effort: 1.5h
---

# Phase 1: Giới hạn vòng sửa chung

## Context

- `factory/orchestrator/states.py`: `MAX_REJECTS = 1`; `after_attempt` chỉ áp giới hạn khi
  `step.gate is None`, nên reject ở gate 1 không bao giờ escalate.
- `factory/orchestrator/runner.py`: `_pass_gate` gọi `after_attempt(..., rejects=0)`; `_run_step`
  đếm `rejected` của riêng station đó.
- Bảng `job` đã có `status = 'rejected'` và `to_status`. Reject ở gate 2 cũng ghi `rejected` nhưng
  `to_status = ESCALATED`, nên phải lọc `to_status = 'DRAFTED'`.

## Yêu cầu

- Một hằng `MAX_REWRITES = 2` thay cho `MAX_REJECTS`, có comment giải thích: số lần một episode được
  gửi về sửa, đếm chung mọi step có `on_reject`.
- `after_attempt(state, outcome, attempt, rewrites)`: khi `outcome == "reject"` và step có `on_reject`,
  nếu `rewrites >= MAX_REWRITES` thì `Move("escalated", ESCALATED)`, ngược lại
  `Move("rejected", on_reject)`. Áp cho cả gate 1 lẫn panel. Gate 2 (không có `on_reject`) giữ nguyên.
- Runner lấy số vòng từ DB, không từ bộ nhớ, để đúng qua nhiều lần `factory run`.

## Files

- Sửa `factory/orchestrator/states.py`: đổi tên hằng, đổi tham số `rejects` thành `rewrites`, bỏ điều
  kiện `step.gate is None` ở nhánh reject.
- Sửa `factory/orchestrator/repo.py`: thêm `count_rewrites(conn, episode) -> int`, đếm job có
  `status = 'rejected' AND to_status = 'DRAFTED'`. (Hằng `State.DRAFTED` truyền vào, không viết chuỗi
  cứng nếu dễ; có thể nhận `to_status` làm tham số.)
- Sửa `factory/orchestrator/runner.py`: `_pass_gate` và `_run_step` truyền
  `repo.count_rewrites(...)`. Khi gate reject bị escalate, job ghi `error` gồm notes của người duyệt
  và câu nói đã hết `MAX_REWRITES` vòng sửa.
- Sửa `tests/test_state_machine.py`, `tests/test_runner.py`.

## Các bước

1. Đổi `states.py` như trên; cập nhật docstring của `after_attempt`.
2. Thêm `repo.count_rewrites`.
3. Nối vào runner. Trong `_run_step`, đếm một lần trước vòng `for` như biến `rejects` hiện tại.
4. Thêm error message khi escalate vì hết vòng (station và gate cùng một câu, ví dụ
   `"rewrite limit reached (2 of 2): <lý do reject>"`).
5. Sửa test.

## Test

- `tests/test_state_machine.py`:
  - đổi `test_panel_reject_rewrites_once_then_escalates` thành kiểm `rewrites = MAX_REWRITES - 1` vẫn
    về `DRAFTED`, `rewrites = MAX_REWRITES` thì `ESCALATED`;
  - thay `test_human_gate_reject_always_returns_to_drafted` bằng test gate 1 tuân theo cùng giới hạn;
  - giữ `test_final_gate_reject_escalates`.
- `tests/test_runner.py` (toy station, cần DB):
  - `test_panel_rejects_once_then_escalates` → panel reject mãi thì job panel là
    `[rejected, rejected, escalated]`;
  - test mới: một reject ở panel cộng một reject ở gate 1 đã dùng hết vòng; reject gate 1 tiếp theo
    escalate (kiểm đếm chung);
  - test mới: reject gate 2 không bị tính vào số vòng.
  - `test_human_reject_at_gate_one_sends_the_script_back` và
    `test_a_rewind_does_not_charge_reused_outputs_again` vẫn pass ở phase này (toy A3 chưa đổi);
    phase 3 cập nhật chúng nếu cần.
- Lệnh: `uv run pytest tests/test_state_machine.py` rồi `uv run pytest tests/test_runner.py`
  (cần `DATABASE_URL`).

## Rủi ro và rollback

- Rủi ro thấp; chỉ đổi luật đếm. Rollback bằng revert file.
