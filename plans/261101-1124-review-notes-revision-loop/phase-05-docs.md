---
phase: 5
title: "Cập nhật docs"
status: completed
effort: 0.5h
---

# Phase 5: Cập nhật docs

## Context

Hành vi người dùng thấy đã đổi: reject có tác dụng, có giới hạn vòng, `decide --decision reject` bắt
buộc notes. Docs evergreen viết bằng tiếng Anh, giữ nguyên ngôn ngữ đó.

## Files

- Sửa `docs/architecture.md`:
  - §5: nói rõ reject đưa ghi chú tới A3 (`RevisionRequest`), A3 sửa từng dòng, "loop budget" là
    `MAX_REWRITES` (2, đếm chung panel và gate 1), quá thì `ESCALATED`.
  - Bảng artifact (§4): thêm `RevisionRequest`.
  - Dòng A3 ở bảng agent: input thêm "or `Script` + reviewer notes".
- Sửa `README.md` nếu có đoạn mô tả `factory decide` hoặc gate 1 (kiểm trước; chỉ sửa khi có).
- Không sửa journal cũ. Journal mới viết ở bước journal sau khi implement, ghi rằng việc còn mở
  trong `plans/journals/2026-10-22-walking-skeleton-implemented.md` đã đóng.

## Test

- Kiểm link tương đối và tên hằng/file trong docs khớp code (`grep MAX_REWRITES`, `revision_request`).
- `docs/architecture.md` vẫn dưới 800 dòng mỗi lần sửa nhỏ (giới hạn `docs.maxLoc`).

## Rủi ro và rollback

- Chỉ là docs; rollback bằng revert.
