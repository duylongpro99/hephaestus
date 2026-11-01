---
title: Media adapter theo mục đích đã có code, chờ smoke test live
date: 2026-11-01
summary: Bốn interface theo mục đích và provider thật (Azure Speech, Cloudflare, DeepInfra, YouTube) xong code và conformance với transport giả; smoke test live chờ secret
---

# Media adapter theo mục đích đã có code

## Đã làm
- Thực thi `plans/261101-0202-purpose-oriented-media-adapters/`: protocol `SpeechSynthesizer`,
  `ImageGenerator`, `VideoRenderer`, `VideoPublisher`; `config/media.yaml` với profile `fake`/`live`;
  registry `factory/adapters/media.py`; ADR 0004.
- Provider thật: Azure Speech (SSML, word boundary, throttle 20 request/phút), Cloudflare Workers AI
  FLUX.2 klein, DeepInfra, YouTube (upload resumable private, `publishAt`, tìm lại theo tag
  `ep-<episode_id>`). Mỗi provider pass conformance với SDK hoặc HTTP giả lập; test `live` chạy khi
  `FACTORY_LIVE_TESTS=1`.
- Lệnh `factory media voices|check|auth youtube` cho smoke test qua đúng code adapter.
- Render 5 phút 1920×1080 mất 22 s trên M1 Pro. Hash output CI không đổi sau khi chuyển renderer.

## Bất ngờ
- `.env` chưa có secret nào của media provider, nên mọi smoke test live còn chờ. Report:
  `plans/reports/smoke-261101-media-providers.md`.
- Review tìm ra lỗi không thấy được khi chỉ có profile `fake`: episode không ghi profile, nên lần
  chạy tiếp có thể publish qua provider khác. Đã thêm migration `0002` (đã backup DB trước).
- `videos.update(part=status)` ghi đè cả status, nên nhãn synthetic media phải lấy lại từ package.
- `test_a_second_runner_on_the_same_episode_is_refused` flaky khoảng 2/25 lần, có từ trước.

## Quyết định
- Không fallback tự động giữa provider; lỗi quota chỉ rõ chỗ cần đổi trong `config/media.yaml`.
- Media profile được ghi vào episode lúc tạo, giống config.

## Bước tiếp
- Người dùng tạo tài khoản và điền `.env`, rồi chạy các lệnh trong report smoke test.
- Đọc điều khoản BFL trước ảnh thật đầu tiên.
- Các mục review chưa sửa: `plans/reports/code-reviewer-261101-0935-media-adapters-review.md`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
