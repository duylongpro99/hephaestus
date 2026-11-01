---
title: Lập plan media adapter theo mục đích
date: 2026-11-01
summary: Plan thay fake TTS/image/render/publish bằng provider thật sau interface theo mục đích
---

# Lập plan media adapter theo mục đích

## What happened
Lập plan `plans/261101-0202-purpose-oriented-media-adapters/` để thay fake media bằng provider của ADR 0003.
Đọc code cho thấy interface hiện có còn rò rỉ provider: `VoiceRef(vendor, id)` trong pack, `LineDirective.vendor/voice_id`,
`rate` theo đơn vị pack đưa thẳng cho TTS, render gọi FFmpeg trực tiếp, CLI hard-code fake.

## Decision
- Bốn interface theo mục đích: `SpeechSynthesizer`, `ImageGenerator`, `VideoRenderer`, `VideoPublisher`;
  chọn provider qua `config/media.yaml`, theo mẫu `config/llm.yaml` của ADR 0002.
- Pack khai báo giọng trừu tượng, channel gán cho cast, media.yaml ánh xạ sang id provider.
- Smoke test chạy qua adapter thật (`factory media check`) ở phase 2–5, sau phase interface.
- Publish chỉ upload private + `publishAt`; phụ đề/thumbnail để plan sau.
- Profile `fake`/`live`; staging và production khác nhau ở `.env`.

## Next steps
Người dùng tạo Azure F0, Cloudflare, Google Cloud project + kênh staging trong lúc làm phase 1.
Bắt đầu bằng `/ak:cook plans/261101-0202-purpose-oriented-media-adapters/plan.md`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
