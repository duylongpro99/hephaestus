# Code review: media adapter theo mục đích (2026-11-01)

Review bằng subagent code-reviewer trên toàn bộ thay đổi chưa commit của plan
[Media adapter theo mục đích](../261101-0202-purpose-oriented-media-adapters/plan.md).
Sau khi sửa: ruff sạch, 271 test pass (3 test `live` bỏ qua), `scripts/ci.sh` pass, hash video CI không đổi.

## Đã sửa

| Mức | Vấn đề | Cách sửa |
|---|---|---|
| High | Media profile không gắn vào episode: chạy tiếp không có flag thì publish qua `export`, hoặc media giả có thể lên YouTube | Migration `0002_episode_media_profile.sql` thêm cột `episode.media_profile`; `factory run` dùng profile đã lưu và từ chối profile khác |
| High | Kênh mới chưa có video: `playlistItems.list` có thể trả 404 `playlistNotFound` nên upload đầu tiên hỏng | `find()` coi lỗi đó là "chưa có video" |
| Medium | Station lỗi giữa chừng làm mất chi phí của các request trước | `MediaError.costs`; worker voice/visuals gắn chi phí đã phát sinh, runner ghi vào ledger |
| Medium | `schedule()` lấy nhãn compliance từ response của API, có thể mất nhãn khi API không trả field | Nhãn lấy từ `PublishPackage`; protocol `schedule(external_id, publish_at, package)` |
| Medium | Upload resumable không retry chunk lỗi | `next_chunk(num_retries=5)` |
| Medium | So khớp `fileDetails.fileName` là code chết | Bỏ; chỉ tìm theo tag `ep-<episode_id>`; ADR 0004 sửa theo |
| Medium | `station_version` không gồm `speech/base.py`, `image/base.py` (`fit_image`, seed) | Thêm hai file đó vào `station_version` |
| Low | Token ghi trước rồi mới chmod; lỗi OAuth ra traceback; token được lưu cả khi tài khoản không có kênh | Ghi file tạm mode 600 rồi `os.replace`; kiểm kênh trước khi lưu; lỗi gọn |
| Low | Token hỏng gây `ValueError` không có hướng dẫn | Đổi thành `PublishError` kèm lệnh auth lại |
| Low | Cloudflare 429 bị báo là hết quota | Tách 429 (rate limit) khỏi mã 4006 (hết quota ngày) |

## Chưa sửa (ghi lại để làm sau)

> Cập nhật 2026-11-01: mọi mục dưới đây đã được xử lý trong plan
> [Gia cố media adapter trước lần chạy live đầu tiên](../261101-1201-media-hardening-before-live/plan.md)
> (marker `publish_attempt` và `factory publish resolve`, dùng lại WAV và dedupe ledger, retry lỗi tạm
> thời của Azure, schedule không tính lại quota, tag `ep-<id>` trong compliance, duration theo frame,
> hệ số `wide_char_units`, rate ngoài khoảng báo lỗi sớm). Các số đo còn phải kiểm khi smoke live nằm
> trong [report smoke](smoke-261101-media-providers.md).

- Video vừa upload có thể chưa hiện trong playlist uploads (eventual consistency). Cần đo trong smoke
  test YouTube trước khi thêm marker "đang upload" trong DB.
- Retry station voice vẫn tổng hợp lại mọi dòng; chưa bỏ qua file WAV đã có. Adapter Azure chưa retry
  `ServiceTimeout`/`ConnectionFailure`.
- `c10_schedule` chạy lại sau crash cộng thêm quota units vào receipt (chỉ sai số đếm).
- Tag `ep-<id>` được thêm sau bước compliance nên không nằm trong giới hạn 500 ký tự tag.
- `duration_s` của Azure lấy từ `audio_duration` thay vì đếm frame WAV; conformance live sẽ bắt chênh lệch.
- Phí Azure tính theo `len(text)`; Azure tính ký tự CJK là 2, cần hệ số khi có pack ja/zh/ko.
- Rate bị kẹp 0.5–2.0 không báo.
