---
phase: 6
title: "Episode staging end-to-end và tài liệu"
status: in-progress
priority: P1
effort: "1d"
dependencies: [2, 3, 4, 5]
---

# Phase 6: Episode staging end-to-end và tài liệu

## Goal

Một episode `en` A2 chạy từ `SPEC` đến `SCHEDULED` với `--media-profile live` trên tài khoản
staging; quy tắc adapter theo mục đích được ghi thành ADR và vào tài liệu.

## Files to Create / Modify

- Create: `docs/decisions/0004-purpose-oriented-media-adapters.md`
- Modify: `docs/decisions/0003-real-media-and-publish-providers.md` (mục "To verify": ghi kết quả, link report)
- Modify: `docs/architecture.md` §7 (worker gọi interface theo mục đích; bảng provider trỏ ADR 0003/0004)
- Modify: `README.md`, `AGENTS.md` (lệnh `factory media ...`, `--media-profile`, `config/media.yaml`)
- Modify: `.env.example`
- Modify: report smoke test (kết luận)

## Tasks & Steps

1. Backup database trước khi chạy episode thật (`pg_dump` vào `../yt-channels-backups/`).
2. Chạy `uv run factory run <spec en A2> --media-profile live` với `.env` staging; duyệt Gate 1 và
   Gate 2 bằng tay (không `--auto-approve`), nghe audio và xem video trước khi duyệt.
3. Kiểm: `AudioManifest` có `words` (nếu F0 hỗ trợ), `CostLedger` có dòng TTS và ảnh, receipt có
   `external_id` thật, video trên kênh staging là private có `publishAt`.
4. Chạy lại cùng lệnh: không upload lại, không gọi lại TTS/ảnh (artifact được tái dùng).
5. Viết ADR 0004 (tiếng Anh, theo mẫu ADR 0002): interface theo mục đích, giọng trừu tượng, profile,
   không auto-fallback, cách thêm provider mới (một module + một `type` + conformance).
6. Cập nhật docs và report.

## Verification

- Episode đạt `SCHEDULED` trên staging; lần chạy thứ hai không tạo side effect mới.
- `scripts/ci.sh` pass.
- Mọi Success Criteria trong `plan.md` được đánh dấu.
