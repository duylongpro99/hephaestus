---
phase: 5
title: "Publishing: YouTube và export"
status: in-progress
priority: P1
effort: "1.5d"
dependencies: [1]
---

# Phase 5: Publishing: YouTube và export

## Goal

`youtube` là implementation của `VideoPublisher`: upload private, đặt `publishAt`, idempotent kể
cả khi crash giữa upload và lưu receipt. Smoke test trên kênh staging riêng tư xác nhận
`publishAt` có hiệu lực với project chưa audit.

## Files to Create / Modify

- Create: `factory/adapters/publishing/youtube.py`
- Modify: `config/media.yaml` (provider `youtube`, `live.publishing`)
- Modify: `factory/cli.py` (`factory media auth youtube`, `factory media check publishing`)
- Modify: `pyproject.toml` (`google-api-python-client`, `google-auth-oauthlib`), `.env.example`, `.gitignore` (thư mục token)
- Create: `tests/adapters/test_youtube_publisher.py`
- Modify: report smoke test

## Tasks & Steps

1. Provider config: `{type: youtube, client_secrets_env: YOUTUBE_CLIENT_SECRETS, token_path_env: YOUTUBE_TOKEN_PATH}`.
   Hai biến trỏ tới file ngoài repo; mỗi môi trường một bộ (ADR 0003).
2. `factory media auth youtube`: chạy OAuth installed-app flow với scope `youtube.upload` và
   `youtube` (cần cho `videos.update`/`videos.list`), lưu refresh token vào `YOUTUBE_TOKEN_PATH`
   quyền 600, in tên kênh để người dùng xác nhận đúng kênh staging. Token không bao giờ in ra.
3. `upload`:
   - Trước khi upload: `channels.list(mine)` → playlist uploads, `playlistItems.list` 50 mục gần
     nhất, `videos.list(part=fileDetails)` tìm `fileName == "<episode_id>.mp4"`. Có thì trả
     `Upload` của video đó, không upload lại (mỗi bước 1 unit).
   - Upload resumable với tên file `<episode_id>.mp4`, `privacyStatus: private`,
     `selfDeclaredMadeForKids`, `containsSyntheticMedia`, title/description/tags theo
     `defaultLanguage` của channel, chapter ghép vào description.
   - `quota_units`: 1 ở bucket upload; ghi riêng units của các lệnh tra cứu.
4. `schedule`: `videos.update(part=status)` với `publishAt` (UTC, RFC 3339) và giữ `private`;
   gọi lại với cùng thời điểm không đổi gì. 50 units.
5. Lỗi: quota hết (`quotaExceeded`) và token hết hạn (`invalid_grant`, gặp khi app ở trạng thái
   Testing sau 7 ngày) thành `PublishError` có hướng dẫn cụ thể (chạy lại `factory media auth youtube`).
6. `ExportPublisher` (từ phase 1) là provider của profile `fake` và là đường lui khi YouTube lỗi:
   ghi MP4 + `metadata.json` để upload tay trong YouTube Studio.
7. Test: dựng request body, tìm video trùng, idempotent schedule, map lỗi; client
   `googleapiclient` được inject bằng `HttpMock`/`HttpMockSequence`.
8. Smoke test trên kênh staging (ghi report):
   - Upload một MP4 ngắn từ phase 4, đặt `publishAt` 1 giờ sau; kiểm video có lên public đúng giờ
     hay bị khóa private vì project chưa audit.
   - Chạy `upload` lần hai cho cùng episode: không có video thứ hai.
   - Quota đã dùng trong Google Cloud console khớp số ghi trong receipt.

## Verification

- `uv run pytest tests/adapters -m "not live"` pass; conformance publishing pass cho `export` và `youtube` (mock).
- Report có kết quả ba mục smoke test.

## Risk

- Video bị khóa private do project chưa audit: ghi vào report, production dùng export cho tới khi
  audit xong; không chặn plan.
- Token và client secret không được nằm trong repo; kiểm `git status` trước mỗi commit.
