---
title: Lập plan gia cố media adapter trước chạy live
date: 2026-11-01
summary: "Plan 5 phase sửa 8 lỗi còn lại từ review media adapter; người dùng chốt marker upload, ledger dedupe và lỗi rate sớm"
---

# Lập plan gia cố media adapter trước chạy live

## Chuyện gì đã xảy ra
Session purpose-oriented-media-adapters-cook chuyển việc lập plan sang session này. Plan nằm ở
`plans/261101-1201-media-hardening-before-live/`, gồm 5 phase và 8 mục lấy từ phần "Chưa sửa" của
`plans/reports/code-reviewer-261101-0935-media-adapters-review.md`. Mới lập plan, chưa implement,
chưa commit.

## Phát hiện khi đọc code
- `ESCALATED` hiện chưa có lệnh resume, nên marker upload cần thêm lệnh `factory publish resolve`.
- Compliance chưa kiểm tra tag, mà `ep-<id>` lại được thêm ở `video_body`, sau bước compliance.
- Media dir của `c5_audio` cố định theo digest của input và version, nên lần retry có thể dùng lại
  WAV đã có.
- Kết nối DB dùng autocommit. Vì vậy `schedule_receipt` commit trước khi job được ghi, và chạy lại
  sẽ cộng quota thêm lần nữa.
- Plan reject-loop không thêm migration, nên plan này dùng `0003` và `0004`.

## Quyết định (người dùng chốt)
- Làm marker upload ngay bằng migration `0004_publish_attempt`. Nếu còn marker mà không thấy video
  thì poll `find()` vài lần rồi escalate.
- Ledger dedupe theo từng dòng: thêm `cost_ledger.dedupe_key` qua migration `0003`, ghi với
  ON CONFLICT DO NOTHING.
- Rate nằm ngoài `rate_range` của provider thì báo lỗi trước request đầu tiên, không kẹp âm thầm.

## Bước tiếp
Người dùng duyệt plan, sau đó chạy `/ak:cook`. Các số đo smoke (độ trễ playlist, upload bị ngắt,
phí request bị cancel) dùng để chỉnh hằng số sau.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
