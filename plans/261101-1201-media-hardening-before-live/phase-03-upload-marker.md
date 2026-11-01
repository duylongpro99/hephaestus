---
title: "YouTube: marker upload và lệnh xử lý"
status: completed
priority: P1
effort: 1d
---

# Phase 3: YouTube: marker upload và lệnh xử lý

## Context

- `factory/adapters/publishing/base.py` (`VideoPublisher`, `PublishError`, `Upload`)
- `factory/adapters/publishing/youtube.py` (`find()`, `upload()`), `factory/adapters/publishing/export.py`
- `factory/workers/publisher.py`, `factory/orchestrator/stations.py` (`upload`), `factory/orchestrator/repo.py`
- `factory/orchestrator/states.py` (`ESCALATED` là trạng thái dừng; hiện chưa có lệnh resume)
- `factory/cli.py`, `factory/orchestrator/migrations/`
- `tests/adapters/test_youtube_publisher.py`, `tests/adapters/conformance.py`, `tests/test_workers.py`,
  `tests/test_runner.py`
- Mục 1 trong [plan](./plan.md). Migration `0004` đứng sau `0003` của phase 2.

## Hiện trạng (đã đọc code)

- `stations.upload`: không có receipt thì gọi `publisher.upload()` (bên trong có `find()` theo tag
  `ep-<id>` trong 50 upload mới nhất, rồi `videos.insert`), sau đó ghi receipt trong một transaction.
- Có một khoảng hở: process chết sau khi `videos.insert` xong nhưng trước khi ghi receipt, và playlist
  uploads chưa có video mới. Lần chạy lại `find()` không thấy, nên upload thêm một bản.
- Connection dùng autocommit, nên một dòng ghi ngoài `transaction()` được commit ngay.

## Thiết kế

Bảng `publish_attempt (episode, platform, started_at, PRIMARY KEY (episode, platform))`.

Luồng mới của `c10_upload`, đặt trong `factory/workers/publisher.py` để giữ code platform-neutral:

1. Đã có receipt: dùng lại như hiện nay.
2. Có marker, chưa có receipt: gọi `publisher.find(episode_id)` tối đa `MARKER_POLLS` lần (mặc định 3),
   cách nhau `MARKER_POLL_INTERVAL_S` (mặc định 60), dùng `ctx.clock.sleep` để test được.
   - Thấy video: ghi receipt (cộng units của mọi lần find) và xóa marker trong một transaction.
   - Không thấy: trả `StationResult("escalate", ...)`. Thông điệp nêu thời điểm của marker và lệnh
     `factory publish resolve`. Không upload.
3. Không có marker: ghi marker (commit ngay), rồi `publisher.upload()`.
   - Thành công: ghi receipt và xóa marker trong cùng một transaction.
   - `PublishError` với `video_may_exist=False` (lỗi trước khi gửi byte đầu tiên, ví dụ token,
     quota, `find()` lỗi, hoặc request khởi tạo bị từ chối): xóa marker rồi raise lại. Runner retry
     như bình thường.
   - Lỗi khác, kể cả exception không phải `PublishError`: giữ marker và raise. Lần retry sau đi vào
     nhánh 2.

Thay đổi protocol `VideoPublisher`:

- Thêm `find(episode_id) -> tuple[str | None, int]`. YouTube đã có hàm này; export tìm file meta có
  `package.episode_id` trùng.
- `PublishError.video_may_exist: bool = True`. YouTube đặt `False` cho lỗi xảy ra trước `next_chunk`
  đầu tiên.

Lệnh `factory publish resolve <episode_id> --platform youtube (--external-id ID | --not-uploaded)`:

- Chỉ chạy khi episode đang `ESCALATED` và job escalated gần nhất là `c10_upload` có marker còn đó.
- `--external-id`: kiểm video qua `publisher.find()` hoặc `videos.list` (cảnh báo nếu tag không khớp),
  ghi receipt, xóa marker, ghi job `c10_upload` do người vận hành thực hiện, rồi chuyển episode
  `ESCALATED → UPLOADED`.
- `--not-uploaded`: người vận hành đã kiểm YouTube Studio và không có video. Xóa marker, ghi job, chuyển
  episode `ESCALATED → FINAL_APPROVED`. `factory run` sẽ upload lại.
- Mỗi lệnh ghi đúng một job trong một transaction, để lịch sử `factory status` thấy được.

## Related code files

- Tạo: `factory/orchestrator/migrations/0004_publish_attempt.sql`
- Sửa: `factory/adapters/publishing/base.py`, `factory/adapters/publishing/youtube.py`,
  `factory/adapters/publishing/export.py`, `factory/workers/publisher.py`,
  `factory/orchestrator/stations.py`, `factory/orchestrator/repo.py`, `factory/cli.py`
- Sửa test: `tests/adapters/test_youtube_publisher.py`, `tests/adapters/conformance.py`,
  `tests/test_workers.py`, `tests/test_runner.py`, test CLI (theo file test CLI hiện có, nếu có)

## Implementation steps

1. Backup DB dev, viết migration `0004`, thêm `repo.get_attempt`, `repo.insert_attempt`,
   `repo.delete_attempt`.
2. Thêm `find()` vào protocol và export, thêm `video_may_exist` vào `PublishError`. Trong YouTube
   `upload()`, bọc phần trước chunk đầu để đặt `video_may_exist=False`. Không gọi `find()` hai lần
   khi worker vừa gọi (truyền kết quả vào, hoặc tách `upload()` thành `find` + `insert`).
3. Viết lại `publisher.upload()` trong worker theo ba nhánh. Hàm nhận `clock` và các hàm repo qua
   tham số, để unit test không cần DB.
4. `stations.upload` gọi worker, đổi kết quả "marker còn, không thấy video" thành escalate.
5. Thêm nhóm lệnh `publish` vào CLI với lệnh `resolve`.
6. Conformance: `find()` trả `(None, units)` cho episode chưa upload, và trả đúng id sau `upload()`.

## Tests (mock, không mạng)

- `test_a_crash_after_insert_does_not_upload_twice` (runner, `-m db`): publisher giả upload xong rồi
  raise như thể process chết; `find()` giả "chậm" trả `None` hai lần rồi trả id. Lần chạy lại không
  gọi `insert`, và receipt có đúng id đó.
- `test_a_marker_without_a_video_escalates_after_polling`: `find()` luôn `None`, `sleep` được gọi
  `MARKER_POLLS - 1` lần với đúng interval, kết quả escalate, không có `insert`.
- `test_an_error_before_any_bytes_clears_the_marker_and_retries` (quota khi khởi tạo).
- `test_an_error_mid_upload_keeps_the_marker` (`next_chunk` lỗi sau chunk đầu).
- `test_success_writes_the_receipt_and_clears_the_marker_together`.
- `test_export_publisher_finds_an_exported_episode`.
- CLI (`-m db`): `test_resolve_with_an_external_id_moves_the_episode_to_uploaded`,
  `test_resolve_not_uploaded_clears_the_marker_and_returns_to_final_approved`,
  `test_resolve_refuses_an_episode_not_escalated_at_upload`.
- Hồi quy: các test YouTube hiện có vẫn pass.

## Todo

- [x] Backup DB dev, migration `0004`, hàm repo cho marker
- [x] `find()` trong protocol và export; `video_may_exist` trong `PublishError`
- [x] Worker publisher theo ba nhánh, poll qua clock
- [x] Station đổi "marker không có video" thành escalate
- [x] `factory publish resolve`
- [x] Test adapter, worker, runner, CLI; cập nhật conformance

## Success criteria

- Không có đường code nào gọi `videos.insert` khi còn marker của episode và platform đó.
- Mọi kịch bản crash trong test đều có tối đa một lần `insert`.
- `scripts/ci.sh` pass với profile `fake` và publisher `export`.

## Cần số đo smoke

- Độ trễ thực tế để video hiện trong playlist uploads, dùng để chỉnh `MARKER_POLLS` và interval.
- Upload resumable bị ngắt có để lại video "processing" hay không, dùng để xác nhận lỗi nào được đặt
  `video_may_exist=False`.

## Risk

- Polling dùng quota: 3 lần × 3 units = 9 units mỗi lần bị kẹt. Không đáng kể so với 10.000/ngày.
- Runner giữ advisory lock trong lúc poll (khoảng 2 phút). Chấp nhận được với runner đồng bộ.

## Security

Lệnh `resolve` không in token. `external_id` được kiểm thuộc kênh của token trước khi ghi receipt.
