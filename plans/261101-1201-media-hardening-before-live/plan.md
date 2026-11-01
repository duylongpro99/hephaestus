---
title: "Gia cố media adapter trước lần chạy live đầu tiên"
description: "Sửa các lỗi còn lại từ review media adapter có thể gây tốn tiền, đăng trùng video hoặc sai sổ chi phí khi chạy provider thật; mọi mục test được bằng mock."
status: completed
priority: P1
effort: 3d
branch: main
tags: [bugfix, backend, orchestrator, database, media]
blockedBy: []
blocks: []
created: 2026-11-01
---

# Gia cố media adapter trước lần chạy live đầu tiên

## Outcome

Trước episode `--media-profile live` đầu tiên, các lỗi còn lại trong mục "Chưa sửa" của
[review media adapter](../reports/code-reviewer-261101-0935-media-adapters-review.md) đã được sửa.
Cụ thể:

1. Chạy lại `c10_upload` sau crash không upload video thứ hai lên YouTube, kể cả khi playlist uploads
   chưa cập nhật.
2. Retry station voice không tổng hợp lại những dòng đã có WAV hợp lệ. Mỗi dòng được ghi vào ledger
   đúng một lần, kể cả khi process bị kill giữa chừng.
3. Adapter Azure retry `ServiceTimeout`, `ConnectionFailure` và `ServiceUnavailable` có giới hạn và
   backoff. Lần gọi thất bại không bị tính phí.
4. Chạy lại `c10_schedule` không cộng thêm quota units vào receipt.
5. Tag `ep-<id>` được tính vào giới hạn 500 ký tự tag của YouTube ngay ở bước compliance.
6. `duration_s` của Azure được tính bằng số frame trong file WAV đã ghi.
7. Phí Azure tính ký tự East Asian wide/fullwidth theo hệ số lấy từ `config/media.yaml`, không
   rẽ nhánh theo mã ngôn ngữ.
8. Rate nằm ngoài khoảng provider hỗ trợ sẽ gây lỗi rõ ràng trước request đầu tiên, không bị kẹp
   âm thầm.

## Constraints

- Không hard-code ngôn ngữ, tuổi hay level trong `factory/`. Hệ số ký tự wide tính theo thuộc tính
  Unicode của từng ký tự và lấy từ config của provider.
- Side effect (upload, schedule, ghi ledger) phải idempotent theo episode và station.
- Không tự động fallback giữa các provider (ADR 0004).
- Thay đổi output của provider phải làm đổi `station_version`. Hiện tại điều này tự xảy ra vì
  `station_version` hash file source của worker và adapter. Phase nào đổi output phải có test xác nhận.
- `scripts/ci.sh` vẫn chạy được mà không cần mạng hay secret. Mọi test mới dùng SDK hoặc transport giả.
- Đổi schema DB thì backup trước (`pg_dump`) và thêm migration mới. Hiện có `0001`, `0002`; plan
  reject-loop không thêm migration nào. Plan này thêm `0003` và `0004`.
- Không đưa mã plan hoặc phase vào code, test, tên migration hay commit message.
- Không in hay commit secret. Chưa commit cho tới khi người dùng yêu cầu.

## Non-goals

- Smoke test live và chọn giọng (vẫn thuộc plan
  [Media adapter theo mục đích](../261101-0202-purpose-oriented-media-adapters/plan.md)).
- Resume resumable upload session của YouTube sau crash (lưu session URI). Marker chỉ ngăn upload mù.
- Lệnh resume chung cho mọi episode `ESCALATED`. Plan chỉ thêm lệnh xử lý marker upload.
- Speech aligner, pack ja/zh/ko, đổi giá Azure.
- Cắt bớt tag tự động ở packager. Compliance chỉ báo lỗi.

## Quyết định đã chốt với người dùng (2026-11-01)

| Câu hỏi | Quyết định |
|---|---|
| Marker upload: làm ngay hay chờ số đo smoke | Làm ngay (migration `0004_publish_attempt`) |
| Còn marker mà không thấy video | Gọi `find()` lại vài lần cách nhau, rồi escalate; thêm lệnh CLI để gắn `external_id` hoặc xóa marker |
| Ledger khi dùng lại WAV | Khóa dedupe theo dòng (`cost_ledger.dedupe_key`, migration `0003`) |
| Rate ngoài khoảng của provider | Lỗi sớm, trước mọi request |

## Phases

| # | Phase | Effort | Mục | Phụ thuộc |
|---|-------|--------|-----|-----------|
| 1 | [Azure Speech: retry, duration, billing, rate range](./phase-01-azure-speech-correctness.md) | 0.5d | 3, 6, 7, 8a | — |
| 2 | [Voice: dùng lại WAV và ledger dedupe](./phase-02-voice-line-reuse-and-ledger-dedupe.md) | 1d | 2, 8b | 1 |
| 3 | [YouTube: marker upload và lệnh xử lý](./phase-03-upload-marker.md) | 1d | 1 | — |
| 4 | [Schedule idempotent và giới hạn tag](./phase-04-schedule-and-tag-limit.md) | 0.25d | 4, 5 | — |
| 5 | [Docs, smoke checklist và CI](./phase-05-docs-smoke-checklist-and-ci.md) | 0.25d | tất cả | 1–4 |

Phase 1, 3 và 4 độc lập nhau. Phase 2 cần `rate_range` từ phase 1. Migration `0003` (phase 2) phải
merge trước `0004` (phase 3); nếu làm song song thì giữ đúng số thứ tự này.

## Mục cần số đo từ smoke live

Code không chờ các số đo này, nhưng hằng số và giả định phải được kiểm lại khi smoke:

| Mục | Cần đo | Ảnh hưởng nếu sai |
|---|---|---|
| 1 | Độ trễ từ lúc `videos.insert` trả về tới lúc video hiện trong playlist uploads | Chỉnh `MARKER_POLLS` và `MARKER_POLL_INTERVAL_S` |
| 1 | Upload resumable bị ngắt giữa chừng có để lại video hay không | Quyết định lỗi nào được xóa marker tự động |
| 3 | Azure có tính phí request bị cancel hay không | Mặc định là không tính |
| 6 | Chênh lệch giữa `audio_duration` và số frame WAV | Chỉ để xác nhận; code dùng số frame |
| 7 | Azure tính ký tự wide là 2 (theo tài liệu giá) | Chỉ kiểm khi có pack CJK; giá trị nằm trong `media.yaml` |

## Acceptance criteria

- [x] Mỗi mục 1–8 có ít nhất một test dùng mock, chạy được khi không có mạng và secret.
- [x] `uv run ruff check .` sạch, `uv run pytest` pass, `scripts/ci.sh` pass.
- [x] Hash video CI (`master.mp4` của xx-fixture) không đổi, hoặc thay đổi được giải thích trong report.
- [x] Migration `0003`, `0004` chạy được trên DB mới (CI) và trên DB dev đã backup.
- [x] ADR 0004 và report smoke ghi lại các quyết định và các mục cần đo.
- [x] Cập nhật mục "Chưa sửa" trong report review, trỏ sang plan này.

## Rủi ro chính

| Rủi ro | Giảm thiểu |
|---|---|
| Marker kẹt làm episode không publish được | Lệnh `factory publish resolve`; tự xóa marker khi chắc chắn chưa có byte nào được gửi |
| Dedupe key gộp nhầm hai lần tổng hợp thật | Key gồm identity của synthesizer và hash đầy đủ của request; chỉ trùng khi output giống hệt |
| Envelope `c5_audio` lớn hơn vì mỗi dòng một CostEntry | Vài chục dòng mỗi episode, chấp nhận được |
