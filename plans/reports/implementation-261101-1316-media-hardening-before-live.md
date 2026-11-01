# Triển khai: gia cố media adapter trước lần chạy live đầu tiên

Plan: [261101-1201-media-hardening-before-live](../261101-1201-media-hardening-before-live/plan.md).
Trạng thái: cả 5 phase xong, chưa commit (theo yêu cầu của plan).

## Kết quả

Tám mục trong plan đều đã có code và test dùng mock, chạy không cần mạng hay secret.

| Mục | Thay đổi chính | Test tiêu biểu |
|---|---|---|
| 1. Không upload hai lần | Bảng `publish_attempt` (migration `0004`); worker publisher ba nhánh (receipt, marker, upload mới); poll `find()` 3 lần cách 60 giây rồi escalate; `factory publish resolve` | `test_a_crash_after_insert_does_not_upload_twice`, `test_a_marker_without_a_video_escalates_after_polling`, các test `test_resolve_*` |
| 2. Voice không tổng hợp lại | File dòng content-addressed `lines/<id>.<key12>.wav` + sidecar ghi atomic; `cost_ledger.dedupe_key` (migration `0003`) với `ON CONFLICT DO NOTHING` | `test_voice_retry_after_a_failure_charges_each_line_once`, `test_a_killed_voice_attempt_*`, `test_keyed_costs_are_recorded_once` |
| 3. Azure retry lỗi tạm thời | Retry `ServiceTimeout`, `ConnectionFailure`, `ServiceUnavailable` trong cùng budget với throttle, backoff 2·2^n tối đa 30 giây; lỗi không tính phí | `test_transient_errors_are_retried_with_backoff`, `test_auth_errors_are_not_retried` |
| 4. Schedule không cộng quota | Bỏ qua API khi receipt đã `scheduled` đúng `publish_at` | `test_schedule_rerun_after_a_crash_keeps_the_quota_count` |
| 5. Tag `ep-<id>` trong giới hạn 500 | `upload_tags()` dùng chung cho `video_body` và compliance; `tags_length()` đếm dấu phẩy và ngoặc kép | `test_compliance_counts_the_episode_tag_against_the_tag_limit` |
| 6. Duration theo frame | `wav_seconds()` đọc file đã ghi, kiểm mono/16-bit/sample rate | `test_duration_comes_from_the_written_frames` |
| 7. Ký tự wide | `billed_chars(text, wide_units)` theo `unicodedata.east_asian_width`; `wide_char_units: 2` trong `config/media.yaml` | `test_wide_characters_are_billed_with_the_configured_units` |
| 8. Rate ngoài khoảng | `rate_range` trong protocol, `check_rate()` báo lỗi; voice kiểm mọi dòng trước request đầu và escalate | `test_rate_outside_the_range_escalates_without_retry` |

## Bằng chứng

- `uv run ruff check .`: sạch.
- `uv run pytest`: 332 passed, 3 skipped (live), sau khi sửa theo review.
- `scripts/ci.sh`: passed in 29s (chạy lại sau khi sửa theo review); migration `0001`–`0004` chạy trên DB mới, lần hai báo "up to date".
- Hash video CI không đổi: receipt `export/export-bc01fd5de9a`, khớp prefix `bc01fd5d…` của `master.mp4`.
- DB dev: backup trước mỗi migration (`backups/20261101-130554-before-cost-ledger-dedupe.sql`,
  `backups/20261101-131113-before-publish-attempt.sql`), rồi `factory db migrate` áp `0003`, `0004`.
  `backups/` đã thêm vào `.gitignore`.

## Khác với plan

- `dedupe_key` của voice là `c4_tts:<thư mục artifact>:<line_id>:<key dòng>` thay vì `c4_tts:<key dòng>`.
  `line_id` giúp hai dòng trùng text, voice và rate vẫn là hai charge. Nếu bỏ thư mục artifact, một lần tổng hợp thật trong artifact khác (ví dụ sau khi script được sửa
  mà một dòng giữ nguyên) sẽ bị bỏ qua trong ledger dù Azure vẫn tính tiền.
- `ESCALATED` vẫn là trạng thái dừng với runner. Lệnh resolve dùng `repo.resolve_upload`, chỉ cho phép
  `ESCALATED → UPLOADED | FINAL_APPROVED` (`UPLOAD_RESOLUTIONS` trong `states.py`), nên test "trạng thái
  dừng không bao giờ chuyển" của state machine vẫn đúng.
- Thêm `video_tags(external_id)` vào protocol `VideoPublisher` để lệnh resolve kiểm video thuộc kênh
  của token (so `snippet.channelId` với kênh `mine`) trước khi ghi receipt.
- Receipt do người vận hành ghi có `quota_units = 0`; 2 units của lần kiểm `video_tags` không được đếm.
- Units của các lần poll `find()` kết thúc bằng escalate không được ghi ở đâu (tối đa 9 units mỗi lần).

## Docs

ADR 0004 (dedupe ledger, `rate_range`, `wide_char_units`, retry Azure, marker upload, `publish resolve`,
schedule, tag), `docs/architecture.md` (§ trạng thái C10, bảng idempotency, data model), README và
AGENTS.md (lệnh `factory publish resolve`). Report smoke có thêm các mục cần đo; report review trỏ mục
"Chưa sửa" sang plan này.

## Review

Xem [report review](code-reviewer-261101-1316-media-hardening-review.md). Đã sửa:

- **High:** câu lặp lại (cùng text, voice, rate) bị ghi vào ledger một lần dù tổng hợp hai lần. Giờ
  `dedupe_key` có thêm `line_id`. Test `test_two_lines_with_the_same_text_are_two_charges` fail với
  code cũ.
- **Medium:** lỗi mạng (timeout, DNS, `TransportError`, `HttpLib2Error`, `OSError`) giờ thành
  `PublishError`. Khi chưa mở session upload thì lỗi mang `video_may_exist=False`, nên marker được
  xóa và station retry. Test: `test_a_network_failure_before_the_upload_session_says_no_video_exists`.
- **Medium:** Azure `wav_seconds` đếm frame thật trên đĩa, không tin header. Nếu không, header
  không khớp sẽ làm mọi lần retry tổng hợp lại.
- **Medium:** `publish resolve` khi không có marker không còn bảo chạy `factory run` (runner không
  chạy episode `ESCALATED`). Giờ lệnh trỏ sang `factory status`.
- **Low:** file meta của export publisher ghi atomic.

Chưa sửa (Low), để lại có chủ đích:

- `factory media check publishing` gọi upload trực tiếp. Đây là lệnh chẩn đoán, không gắn với episode.
- Crash đúng giữa lúc ghi WAV và ghi sidecar làm mất phí một dòng. Ledger vẫn là mức sàn, như ADR ghi.
- `station_version` của compliance không theo đổi của `publishing/base.py`.

## Câu hỏi còn mở

- `resolve --external-id` có nên bắt buộc `--force` khi video thiếu tag `ep-<id>` không? Hiện tại lệnh
  chỉ cảnh báo.
- Có cho `--not-uploaded` chạy khi không còn marker không? Plan đã đặt "lệnh resume chung" là non-goal.

- Các hằng số `MARKER_POLLS` và `MARKER_POLL_INTERVAL_S`, cách đếm tag và việc upload bị ngắt có để lại
  video hay không vẫn chờ số đo từ smoke live.
