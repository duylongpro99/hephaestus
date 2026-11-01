---
title: Lập plan vòng sửa script sau reject
date: 2026-11-01
summary: "Reject ở panel/gate 1 hiện là no-op do cache; plan cho A3 sửa theo ghi chú reviewer, tối đa 2 vòng"
---

# Lập plan vòng sửa script sau reject

## What happened
- Session khác chuyển việc sang: ghi chú reviewer không tới A2/A3 khi reject.
- Scout cho thấy nguyên nhân sâu hơn: reject về `DRAFTED` chỉ chạy lại A3 với input y hệt, nên store content-addressed trả đúng script cũ ($0, không gọi LLM). `level_loop` cũng bỏ qua LLM khi level gate pass. Panel escalate sau reject thứ hai; gate 1 lặp lại script cũ vô hạn.

## Decision
Người dùng chọn: tự sửa có giới hạn; A3 sửa từng dòng (giữ `on_reject = DRAFTED`); `MAX_REWRITES = 2` hằng số code, đếm chung panel và gate 1; dùng `QAIssue` sẵn có + notes text, thêm contract `RevisionRequest` 1.0.0, không migration.

## Next steps
- Implement theo `plans/261101-1124-review-notes-revision-loop/plan.md` (5 phase) qua `/ak:cook`.
- Đổi `a3.version` sẽ vô hiệu cache A3 cũ.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
