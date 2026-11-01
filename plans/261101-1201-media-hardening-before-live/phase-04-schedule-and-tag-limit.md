---
title: "Schedule idempotent và giới hạn tag"
status: completed
priority: P2
effort: 0.25d
---

# Phase 4: Schedule idempotent và giới hạn tag

## Context

- `factory/workers/publisher.py` (`schedule()`), `factory/orchestrator/stations.py` (`schedule`)
- `factory/workers/compliance.py`, `factory/adapters/publishing/youtube.py` (`episode_tag`, `video_body`),
  `factory/adapters/publishing/base.py`
- `tests/test_workers.py`, `tests/test_runner.py`, `tests/adapters/test_youtube_publisher.py`
- Mục 4 và 5 trong [plan](./plan.md).

## Hiện trạng (đã đọc code)

- `stations.schedule` gọi API, rồi `repo.schedule_receipt` (autocommit, commit ngay), rồi produce
  artifact, rồi runner ghi job. Nếu crash sau khi DB đã ghi `status='scheduled'` nhưng trước khi ghi
  job, lần chạy lại gọi `publisher.schedule()` một lần nữa (1 unit) và cộng thêm vào
  `receipt.quota_units` vốn đã gồm lần trước.
- Compliance kiểm title và description, **không** kiểm tag. `video_body` thêm `ep-<id>` sau đó.

## Requirements

1. **Schedule không tính lại.** Trong `publisher.schedule()` của worker: nếu
   `receipt.status == "scheduled"` và `receipt.publish_at == publish_at` thì trả receipt nguyên trạng,
   không gọi API. Lý do: receipt chỉ thành `scheduled` sau khi API đã thành công. Trường hợp API đã chạy
   mà DB chưa ghi vẫn gọi lại (idempotent ở phía YouTube); units của lần đó là chi phí thật, nên được
   cộng là đúng.
2. **Giới hạn tag.** Chuyển `episode_tag()` sang `factory/adapters/publishing/base.py` vì đây là quy ước
   chung để tìm lại upload. YouTube import từ đó. Compliance thêm `TAGS_MAX = 500` và
   `tags_length(tags)` theo cách YouTube đếm: tổng độ dài các tag, cộng một dấu phẩy giữa hai tag, cộng
   2 cho tag có khoảng trắng (vì được bọc trong ngoặc kép). Compliance kiểm
   `[*package.tags[lang], episode_tag(package.episode_id)]` cho từng support language, và báo lỗi nếu vượt.
   Cách đếm này dùng chung với `video_body` để hai nơi không lệch nhau.

## Related code files

- Sửa: `factory/workers/publisher.py`, `factory/workers/compliance.py`,
  `factory/adapters/publishing/base.py`, `factory/adapters/publishing/youtube.py`
- Sửa test: `tests/test_workers.py`, `tests/test_runner.py`, `tests/adapters/test_youtube_publisher.py`

## Tests (mock, không mạng)

- `test_rescheduling_an_already_scheduled_receipt_spends_no_quota`: publisher giả đếm lời gọi bằng 0,
  và `quota_units` không đổi.
- `test_a_receipt_scheduled_at_another_time_is_scheduled_again` (đổi slot thì vẫn gọi API).
- Runner (`-m db`): `test_schedule_rerun_after_a_crash_keeps_the_quota_count`: mô phỏng crash sau
  `schedule_receipt`, chạy lại, kiểm `quota_units` bằng lần đầu.
- `test_compliance_counts_the_episode_tag_against_the_tag_limit`: tag gần 500 ký tự, chỉ vượt khi
  cộng `ep-<id>`.
- `test_tags_length_counts_commas_and_quotes_for_spaces`.

## Todo

- [x] Bỏ qua API khi receipt đã scheduled đúng slot
- [x] Chuyển `episode_tag` sang base; `tags_length` và `TAGS_MAX` trong compliance
- [x] Test worker, compliance, runner

## Success criteria

- Chạy lại `c10_schedule` sau crash không làm đổi `quota_units`.
- Package có tag vừa đủ 500 mà chưa tính `ep-<id>` sẽ bị compliance chặn trước gate 2, không phải
  lỗi API ở bước upload.
- `station_version` của `a11_compliance` đổi (source đổi), nên report compliance cũ không được dùng lại.

## Risk

- Cách YouTube đếm tag không có tài liệu chính thức. Thêm vào checklist smoke: upload một package
  có tag gần 500 ký tự lên kênh staging và xem API có chấp nhận không.
