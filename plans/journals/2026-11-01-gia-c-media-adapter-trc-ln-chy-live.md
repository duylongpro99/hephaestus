---
title: Gia cố media adapter trước lần chạy live
date: 2026-11-01
summary: "Upload không trùng nhờ marker, ledger voice không đếm sai, Azure retry lỗi tạm thời; review bắt được bug ledger với câu lặp"
---

# Gia cố media adapter trước lần chạy live

## Chuyện gì đã xảy ra

Plan `261101-1201-media-hardening-before-live` có 5 phase, chạy ở chế độ `--auto`. Các thay đổi chính:

- Bảng `publish_attempt` (migration `0004`) là marker ghi trước khi gửi byte đầu tiên lên YouTube. Nếu chạy lại mà còn marker, worker poll `find()` 3 lần rồi escalate. Người vận hành gỡ escalation bằng `factory publish resolve`.
- Voice lưu từng dòng theo content-address, kèm sidecar. `cost_ledger.dedupe_key` (migration `0003`) có `ON CONFLICT DO NOTHING`, nên retry không tính tiền lại.
- Azure retry `ServiceTimeout`, `ConnectionFailure` và `ServiceUnavailable` có backoff. Thêm kiểm `rate_range`, tính ký tự wide là 2 đơn vị, duration lấy theo số frame.
- Schedule không gọi API khi đã đúng `publish_at`. Compliance đếm cả tag `ep-<id>` vào giới hạn 500.

## Review bắt được gì

Bug High: hai dòng cùng text, voice và rate (câu drill lặp) được tổng hợp hai lần nhưng ledger chỉ ghi một, vì `dedupe_key` không có `line_id`. Hệ quả là budget guard bị đánh giá thấp. Đã sửa bằng `c4_tts:<dir>:<line_id>:<key>`, và test mới fail với code cũ.

Đã sửa thêm:
- Lỗi mạng trước khi mở session upload giờ thành `PublishError(video_may_exist=False)`.
- Azure đếm frame thật thay vì tin header.
- Thông báo của `publish resolve` không còn bảo chạy `factory run`.
- File meta của export ghi atomic.

## Quyết định

- `ESCALATED` vẫn là trạng thái dừng. Chỉ `resolve_upload` được chuyển sang `UPLOADED` hoặc `FINAL_APPROVED`.
- Không tự fallback giữa các provider. Ledger là mức sàn khi crash giữa lúc ghi WAV và ghi sidecar.

## Bước tiếp theo

- Smoke live (Azure, YouTube staging) để chỉnh `MARKER_POLLS` và `MARKER_POLL_INTERVAL_S`, xác nhận cách đếm tag và xem upload bị ngắt có để lại video không.
- Người dùng quyết: `resolve --external-id` có cần `--force` khi video thiếu tag không; `--not-uploaded` có chạy khi không còn marker không.
- Chưa commit.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
