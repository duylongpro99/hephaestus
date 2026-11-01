# Smoke test media provider (2026-11-01)

Report dùng chung cho phase 2–6 của plan
[Media adapter theo mục đích](../261101-0202-purpose-oriented-media-adapters/plan.md).
Mọi lệnh chạy qua adapter thật (`factory media check ...`), cùng code mà episode dùng.

## Trạng thái

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Render 5 phút (phase 4) | **Xong** | Xem bên dưới |
| Azure Speech F0 (phase 2) | Chờ secret | `.env` chưa có `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` |
| Cloudflare Workers AI free (phase 3) | Chờ secret | Chưa có `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` |
| DeepInfra (phase 3, dự phòng) | Chờ secret | Chưa có `DEEPINFRA_API_KEY` |
| YouTube staging (phase 5) | Chờ secret | Chưa có OAuth client và kênh staging |
| Episode staging `--media-profile live` (phase 6) | Chờ các mục trên | |
| Điều khoản BFL | Người dùng chưa xác nhận đã đọc | Bắt buộc trước ảnh thật đầu tiên (ADR 0003) |

Toàn bộ code của bốn provider thật đã có và pass conformance với transport giả lập
(`uv run pytest tests/adapters`). Các test `live` đã viết sẵn, chạy bằng
`FACTORY_LIVE_TESTS=1 uv run pytest -m live`.

## Render 5 phút (FFmpeg + Pillow)

- Input: `RenderProps` 300 s, 1920×1080, 30 fps, 10 scene, 80 caption, audio sine và ảnh màu đơn
  (dựng bằng fake provider).
- Lệnh: `uv run factory media check video --props <props.json> --artifacts <store> --pack en`.
- Kết quả trên Apple M1 Pro (10 nhân): **22,0 s** render, file 4,3 MB, RSS đỉnh khoảng 1,8 GB
  (`/usr/bin/time -l`), CPU 104 s user.
- Identity: `ffmpeg_pillow/ffmpeg version 9.0.2 ...; pillow 13.0.0; font default` (pack `en`
  chưa có file font nên dùng font mặc định của Pillow).
- Output CI không đổi sau khi chuyển renderer: hash `master.mp4` của episode xx-fixture vẫn là
  `bc01fd5d…f5cd083`, audio `2fc4a57f…a5248d`.

## Cần chạy khi có secret

### Speech (Azure F0)

```bash
uv run factory media voices --profile live
uv run factory media check speech --profile live --voice en-gb-female-1 --rate 0.8 \
  --text "Excuse me, where is the train station, please?"
uv run factory media check speech --profile live --voice en-gb-male-1 --rate 1.0 --text "..."
FACTORY_LIVE_TESTS=1 uv run pytest -m live tests/adapters/test_azure_speech.py -s
```

Ghi lại:

- [ ] `word timings: N` khác 0 trên F0 (nếu `none`: giữ `words=None`, đề xuất aligner ở plan sau).
- [ ] Nghe ở rate chậm của band A2 (`band.rate.min / native_rate`) và rate 1.0 cho 2–3 giọng en-GB
      mỗi giới; chọn giọng cho Anna và Ben, ghi vào `profiles.live.speech.voices`.
- [ ] Thời gian cho 80 câu khi bị throttle 20 request/phút (ước tính khoảng 4 phút).
- [ ] Giá S0 trên Azure portal khớp `prices.azure-speech.neural` ($16/1M ký tự).

### Image (Cloudflare free, DeepInfra)

```bash
uv run factory media check image --profile live --prompt "a quiet train station at dawn"
```

- [ ] REST trên free plan chạy được với token quyền Workers AI.
- [ ] Request multipart (`prompt`, `width`, `height`, `seed`) được chấp nhận; response có
      `result.image` base64. Đây là phần doc chưa rõ nhất, cần xác nhận đầu tiên.
- [ ] Số neuron mỗi ảnh 1024×576 (trong dashboard) so với ước tính 80; thời gian mỗi ảnh.
- [ ] Chất lượng 3 prompt mẫu theo segment type; kết quả sau `fit_image` lên 1920×1080.
- [ ] DeepInfra: endpoint OpenAI-compatible nhận `response_format: b64_json`. Endpoint này không
      nhận `seed`, nên ảnh DeepInfra không lặp lại được khi chạy lại (artifact vẫn được tái dùng
      theo `station_version`).

### Publishing (YouTube staging)

```bash
uv run factory media auth youtube --profile live   # in tên kênh: xác nhận đúng kênh staging
uv run factory media check publishing --profile live --video <mp4 ngắn> --package <package.json>
uv run factory media check publishing --profile live --video <cùng mp4> --package <cùng package>
```

- [ ] Video private, `publishAt` 1 giờ sau; kiểm video có lên public đúng giờ hay bị khóa private
      vì project chưa audit.
- [ ] Lần upload đầu lên kênh chưa có video: `playlistItems.list` trả 404 `playlistNotFound`
      (code coi là "chưa có video") hay `items: []`.
- [ ] Lần chạy thứ hai không tạo video thứ hai (tìm theo tag `ep-<episode_id>` trong 50 upload
      gần nhất).
- [ ] Video vừa upload hiện trong playlist uploads sau bao lâu. Nếu trễ, một crash ngay sau upload
      rồi chạy lại ngay vẫn có thể upload lần hai; khi đó cần thêm marker "đang upload" trong DB.
- [ ] Sau `schedule`, video giữ nhãn `containsSyntheticMedia` và `selfDeclaredMadeForKids` đúng
      như package.
- [ ] Quota trong Google Cloud console khớp số in ra (receipt chỉ đếm bucket 10K).

### Episode staging

Backup database trước (`pg_dump` vào `../yt-channels-backups/`), rồi:

```bash
uv run factory run evals/en/adult/specs/en-A2-x01.json --media-profile live
```

Duyệt Gate 1 và Gate 2 bằng tay; kiểm `words` trong AudioManifest, dòng TTS và ảnh trong
CostLedger, receipt có `external_id` thật; chạy lại không upload lần hai.

## Ghi chú kỹ thuật

- Cloudflare: URL `https://api.cloudflare.com/client/v4/accounts/{id}/ai/run/@cf/black-forest-labs/flux-2-klein-4b`
  suy ra từ mẫu REST chung; doc của model mô tả input dạng multipart.
- Lỗi quota Cloudflare (code 4006 hoặc HTTP 429) và DeepInfra (402/429) báo rõ cần đổi provider
  trong `config/media.yaml`; không có fallback tự động.
- Test có sẵn `tests/test_runner.py::test_a_second_runner_on_the_same_episode_is_refused` flaky
  khoảng 2/25 lần (Postgres nhả advisory lock bất đồng bộ sau khi đóng connection). Không thuộc
  thay đổi này; `scripts/ci.sh` từng fail một lần vì nó.
