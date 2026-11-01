---
title: "Docs, smoke checklist và CI"
status: completed
priority: P2
effort: 0.25d
---

# Phase 5: Docs, smoke checklist và CI

## Context

- `docs/decisions/0004-purpose-oriented-media-adapters.md`, `docs/architecture.md` (§4.4, §5 publisher),
  `README.md`, `AGENTS.md` (mục Lệnh)
- [Report smoke](../reports/smoke-261101-media-providers.md),
  [report review](../reports/code-reviewer-261101-0935-media-adapters-review.md)
- `scripts/ci.sh`

## Requirements

1. ADR 0004: ghi marker `publish_attempt` và quy tắc không upload khi còn marker, lệnh
   `factory publish resolve`, retry lỗi tạm thời của Azure, `rate_range` và lỗi sớm, option
   `wide_char_units`, và dedupe ledger theo dòng.
2. `docs/architecture.md`: sửa đoạn mô tả idempotency của C10 và cách ledger ghi chi phí media. Chỉ sửa
   những câu đã sai, giữ tiếng Anh.
3. README và AGENTS.md: thêm `factory publish resolve` vào danh sách lệnh.
4. Report smoke: thêm các mục cần đo, gồm độ trễ playlist uploads, upload bị ngắt có để lại video
   không, Azure có tính phí request bị cancel không, chênh lệch `audio_duration` với số frame, và tag
   gần 500 ký tự.
5. Report review: ở mục "Chưa sửa", ghi rằng các mục đã được xử lý trong plan này, kèm link.
6. Chạy toàn bộ quality gate.

## Implementation steps

1. Sửa docs theo danh sách trên. Đọc file trước khi sửa.
2. `uv run ruff check .`
3. `uv run pytest`
4. `scripts/ci.sh`, rồi so hash `master.mp4` của xx-fixture với `bc01fd5d…f5cd083`. Nếu đổi thì giải
   thích trong report triển khai.
5. Kiểm link trong các file đã sửa.

## Todo

- [x] ADR 0004, architecture, README, AGENTS.md
- [x] Checklist smoke có các mục cần đo
- [x] Report review trỏ sang plan này
- [x] ruff, pytest, `scripts/ci.sh` pass; ghi kết quả hash

## Success criteria

Mọi acceptance criteria trong [plan](./plan.md) được tick, kèm bằng chứng từ lệnh đã chạy.
