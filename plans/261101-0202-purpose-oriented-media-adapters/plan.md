---
title: "Media adapter theo mục đích và provider thật"
description: "Thay các fake TTS, image, render và publish bằng provider thật theo ADR 0003, sau các interface đặt theo mục đích mà mọi provider chỉ cần tương thích."
status: in-progress
priority: P1
effort: 7.5d
tags: [feature, backend, infra]
blockedBy: []
blocks: []
created: 2026-11-01
---

# Media adapter theo mục đích và provider thật

## Overview

Walking skeleton đã đưa một episode từ `SPEC` đến `SCHEDULED` với TTS, image và publish giả
cùng một bản render FFmpeg placeholder. [ADR 0003](../../docs/decisions/0003-real-media-and-publish-providers.md)
đã chọn provider thật: Azure Speech, FLUX.2 [klein] trên Cloudflare Workers AI (DeepInfra dự
phòng), FFmpeg + Pillow, YouTube Data API v3.

Yêu cầu của người dùng (2026-11-01): **adapter phải abstract theo mục đích, không dành riêng cho
provider.** Station và worker chỉ biết "tổng hợp giọng nói", "tạo ảnh", "dựng video", "đăng
video". Azure, Cloudflare, YouTube là các implementation tương thích với interface đó; đổi
provider là đổi config, không sửa station.

## Hiện trạng (đã đọc code)

Interface hiện có gần đúng hướng nhưng còn rò rỉ provider ở nhiều chỗ:

| Chỗ | Vấn đề |
|---|---|
| `factory/tools/language_pack.py` `VoiceRef(vendor, id)` | Pack giữ id giọng của vendor, nên đổi provider là phải sửa pack. |
| `factory/contracts/voice_directives.py` `LineDirective.vendor`, `voice_id` | Contract mang tên vendor và id giọng của vendor. |
| `factory/workers/voice.py` `cast_voices` | Gán giọng theo thứ tự cast, nên Anna có thể nhận giọng nam. |
| `TTSProvider.synthesize(text, voice, rate, out)` | `rate` theo đơn vị của pack (wpm), mỗi provider phải tự hiểu pack; chỉ trả thời lượng, không trả word timing hay chi phí. |
| `ImageProvider.generate(...)` | Không trả chi phí; không quy định khi model không sinh được đúng kích thước. |
| `factory/workers/render.py` | Render gọi FFmpeg trực tiếp, không có interface; Remotion sau này phải sửa worker. |
| `factory/cli.py` `run_cmd` | Fake được hard-code; không có cách chọn provider. |
| Thuộc tính `vendor` trên các Protocol | Lộ khái niệm vendor ra ngoài interface; `identity` đã đủ cho `station_version`. |

LLM đã làm đúng mẫu này: `LLMProvider` + `config/llm.yaml` + `router.provider_for(role)`
(ADR 0002). Plan này áp dụng cùng mẫu cho media.

## Brainstorm contract

- **Outcome:** một episode `en` A2 chạy hết pipeline trên staging với giọng Azure F0, ảnh
  Cloudflare free, render FFmpeg + Pillow và được đặt lịch trên kênh YouTube staging riêng tư;
  CI vẫn chạy toàn fake, không mạng. Các mục "To verify at the first smoke test" của ADR 0003
  có kết quả ghi lại.
- **Constraints:**
  - Interface đặt tên theo mục đích (`SpeechSynthesizer`, `ImageGenerator`, `VideoRenderer`,
    `VideoPublisher`); không type, field hay tham số nào trong interface, contract, pack hay
    worker mang tên vendor.
  - Provider chọn bằng `config/media.yaml` (giống `config/llm.yaml`); secret chỉ ở `.env`.
  - Không chạy model local (ADR 0003). Không tự động fallback giữa provider; operator đổi config.
  - Không code chặn output phi thương mại sang production (quyết định người dùng 2026-10-31).
  - Side effect publish idempotent theo episode và station.
  - `scripts/ci.sh` giữ nguyên tính chất: không mạng, không secret.
- **Non-goals:**
  - Speech aligner (Whisper) và Amazon Polly: chỉ làm nếu smoke test cho thấy F0 không có
    `WordBoundary`.
  - Remotion; giọng `vi`; Shorts.
  - Phụ đề (`captions.insert`), thumbnail (`thumbnails.set`) và playlist: chưa có artifact nào
    tạo ra chúng; làm ở plan sau.
  - Dòng "AI-generated voices" trong mô tả video (follow-up của ADR 0003, thuộc A9 packaging).
  - Console, notify, analytics.
- **Acceptance criteria:** xem Success Criteria.

## Thiết kế

```
station/worker ──> purpose interface ──> registry(profile) ──> provider implementation
  voice.py           SpeechSynthesizer      config/media.yaml     fake | azure_speech
  visuals.py         ImageGenerator                               fake | cloudflare_workers_ai | deepinfra
  render.py          VideoRenderer                                ffmpeg_pillow
  publisher.py       VideoPublisher                               export | youtube
```

- **Một package cho mỗi mục đích** dưới `factory/adapters/`: `speech/`, `image/`, `video/`,
  `publishing/`. Mỗi package có `base.py` (Protocol + request/result dataclass) và một module cho
  mỗi provider. `factory/adapters/media.py` đọc `config/media.yaml` và dựng implementation theo
  `type`, giống `llm/router.py`.
- **Request trung lập:** `SpeechRequest(text, language, voice, rate)` trong đó `voice` là key
  giọng trừu tượng của pack và `rate` là tỉ lệ so với tốc độ nói tự nhiên của pack (1.0 = native).
  Worker quy đổi đơn vị của pack (wpm, mora/s, ...) sang tỉ lệ này, nên provider không cần biết pack.
- **Giọng:** pack khai báo các giọng trừu tượng (`VoiceSpec(key, locale, gender, tags)`), channel
  gán key cho từng cast member, còn `config/media.yaml` ánh xạ key sang id giọng của provider đang
  dùng. Đổi provider TTS chỉ đổi bảng ánh xạ.
- **Kết quả có chi phí:** mọi call trả `CostEntry`, giá đọc từ `config/media.yaml` như `prices`
  của LLM; provider không có giá thì ghi `priced: false`.
- **Profile:** `fake` (mặc định, CI) và `live`. Dev và staging khác production chỉ ở `.env`
  (resource Azure, token Cloudflare, OAuth token của kênh), đúng cách tách môi trường của ADR 0003.
- **Conformance test theo mục đích:** mỗi Protocol có một bộ test chung mà mọi implementation
  phải pass (giống conformance của pack); provider thật chạy bộ đó với transport giả lập, và
  chạy thật khi có secret (marker `live`).

## Phases

| # | Phase | Effort | Depends on | Status |
|---|---|---|---|---|
| 1 | [Interface theo mục đích, media config, registry](./phase-01-purpose-interfaces-and-registry.md) | 2d | none | Completed |
| 2 | [Speech: Azure và smoke test giọng](./phase-02-speech-azure-and-smoke.md) | 1.5d | 1 | Code xong, chờ smoke live |
| 3 | [Image: Cloudflare, DeepInfra và smoke test](./phase-03-image-cloudflare-and-smoke.md) | 1d | 1 | Code xong, chờ smoke live |
| 4 | [Video renderer và đo thời gian render](./phase-04-video-renderer.md) | 0.5d | 1 | Completed |
| 5 | [Publishing: YouTube và export](./phase-05-publishing-youtube.md) | 1.5d | 1 | Code xong, chờ smoke live |
| 6 | [Episode staging end-to-end và tài liệu](./phase-06-staging-episode-and-docs.md) | 1d | 2, 3, 4, 5 | Docs xong, chờ episode staging |

Phase 2–5 độc lập với nhau sau phase 1. Smoke test của từng provider nằm ngay trong phase của
provider đó, chạy qua lệnh `factory media check <purpose>`, trước khi episode staging ở phase 6
dùng tới nó.

**Vì sao phase 1 không phải là smoke test:** smoke test chạy qua adapter thật để không phải viết
code gọi vendor hai lần (một bản probe, một bản adapter). Phase 1 không gọi mạng và không cần tài
khoản, nên trong lúc làm phase 1 người dùng tạo tài khoản ở bước chuẩn bị bên dưới.

## Chuẩn bị của người dùng (song song với phase 1)

| Việc | Cần cho | Biến trong `.env` |
|---|---|---|
| Tạo Azure Speech resource **F0** (staging), ghi region | Phase 2 | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` |
| Tạo tài khoản Cloudflare, API token quyền Workers AI | Phase 3 | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` |
| (Tùy chọn) Tài khoản DeepInfra | Phase 3 fallback | `DEEPINFRA_API_KEY` |
| Tạo Google Cloud project staging, bật YouTube Data API v3, OAuth client loại Desktop, kênh YouTube staging riêng tư | Phase 5 | `YOUTUBE_CLIENT_SECRETS`, `YOUTUBE_TOKEN_PATH` |
| Đọc điều khoản BFL trước ảnh thật đầu tiên (ADR 0003) | Phase 3 | không |

## Success Criteria

Tiến độ và các mục còn chờ secret: [report smoke test](../reports/smoke-261101-media-providers.md).

- [x] `scripts/ci.sh` pass với profile `fake`, không mạng, không secret.
- [x] `grep -rniE "azure|cloudflare|deepinfra|flux|neural" factory/workers factory/contracts factory/orchestrator packs`
      không trả kết quả nào; tên provider chỉ xuất hiện trong module provider, `config/media.yaml` và tài liệu.
      YouTube vẫn được nhắc ở packaging và compliance vì đó là nền tảng đích (giới hạn metadata), không phải adapter.
- [x] Mọi implementation pass bộ conformance test của mục đích tương ứng.
- [ ] `factory media check speech|image|publishing` chạy thật trên tài khoản staging; kết quả từng
      mục "To verify" của ADR 0003 được ghi vào report smoke test.
- [ ] Một episode `en` A2 với `--media-profile live` đạt `SCHEDULED` trên kênh staging; chạy lại
      lệnh không upload lần hai.
- [ ] Chi phí TTS và ảnh xuất hiện trong `CostLedger` của episode.
- [x] Docs cập nhật: ADR 0004 cho quy tắc adapter theo mục đích, `architecture.md` §7, `README`/`AGENTS.md`
      phần lệnh, `.env.example`.

## Risks

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| F0 không trả `WordBoundary` | `LineAudio.words` rỗng | Interface để word timing là tùy chọn; thêm aligner ở plan sau nếu cần. |
| F0 throttle 20 transaction/60 s | Episode staging chậm khoảng 4 phút | Provider tự giới hạn tốc độ và retry theo `Retry-After`. |
| Kích thước ảnh FLUX klein khác 1920×1080 | Ảnh méo | Helper chung `fit_image` crop/scale về kích thước yêu cầu. |
| Upload YouTube xong nhưng crash trước khi lưu receipt | Upload trùng | Adapter tìm video theo tên file gốc (`fileDetails.fileName`) trước khi upload. |
| Project YouTube chưa audit ép video private | `publishAt` không có hiệu lực | Smoke test ở phase 5 kiểm tra; export package là đường lui. |
| Thay contract `LineDirective` | Artifact cũ không đọc được | Tăng `schema_version`; artifact cũ chỉ là dữ liệu test, `station_version` đổi nên không bị tái dùng. |

## Decisions (người dùng, 2026-11-01)

| Quyết định | Giá trị |
|---|---|
| Adapter | Abstract theo mục đích; provider chỉ là implementation tương thích |
| Id giọng của provider | Pack khai báo giọng trừu tượng, channel gán cho cast, `config/media.yaml` ánh xạ sang id provider |
| Smoke test | Chạy qua adapter thật ở phase 2–5 (`factory media check`), sau phase interface |
| Publish | Upload private + `publishAt`, chống upload trùng; phụ đề, thumbnail, playlist để plan sau |
| Chọn provider theo môi trường | Profile `fake` / `live`; staging và production khác nhau ở `.env` |
