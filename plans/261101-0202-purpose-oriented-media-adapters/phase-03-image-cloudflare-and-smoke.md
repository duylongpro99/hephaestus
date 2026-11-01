---
phase: 3
title: "Image: Cloudflare, DeepInfra và smoke test"
status: in-progress
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 3: Image: Cloudflare, DeepInfra và smoke test

## Goal

`cloudflare_workers_ai` và `deepinfra` là hai implementation của `ImageGenerator` cho cùng model
FLUX.2 [klein] 4B, chọn bằng config; smoke test xác nhận free plan của Cloudflare gọi được qua REST
và chi phí mỗi ảnh khớp ước tính.

## Files to Create / Modify

- Create: `factory/adapters/image/cloudflare_workers_ai.py`, `factory/adapters/image/deepinfra.py`
- Modify: `config/media.yaml` (hai provider, `live.image`, giá)
- Modify: `factory/cli.py` (`factory media check image`)
- Modify: `.env.example`
- Create: `tests/adapters/test_image_providers.py`
- Modify: report smoke test

## Tasks & Steps

1. Provider config:
   - `{type: cloudflare_workers_ai, account_id_env: CLOUDFLARE_ACCOUNT_ID, api_key_env: CLOUDFLARE_API_TOKEN}`
   - `{type: deepinfra, api_key_env: DEEPINFRA_API_KEY}`
   - `live.image: {provider: cloudflare, model: "@cf/black-forest-labs/flux-2-klein-4b", width: 1024, height: 576}`.
     `width/height` là kích thước gửi cho model; adapter gọi `fit_image` để ra kích thước của request.
2. Gọi HTTP bằng `httpx` (đã có qua `openai`; khai báo trực tiếp trong `pyproject.toml`), timeout,
   decode ảnh base64 hoặc bytes theo response của từng API (kiểm lại doc hiện hành khi làm).
3. Lỗi quota của free plan (Cloudflare trả lỗi, không tính tiền) thành `ImageError` nói rõ "đổi
   `live.image.provider` sang deepinfra trong config/media.yaml". Không tự fallback.
4. Prompt: thêm hậu tố cố định trong config (`style_suffix`) cho phong cách kênh; không đưa người
   thật, thương hiệu hay chữ vào prompt (chữ do renderer vẽ). Việc dựng prompt giữ ở `visuals.py`.
5. `seed` gửi theo request để ảnh lặp lại được khi provider hỗ trợ.
6. Chi phí: Cloudflare tính theo neuron, ghi `usd` theo giá vượt free tier và một trường note
   trong `model`; DeepInfra theo giá mỗi ảnh.
7. `factory media check image --profile live --prompt "..." --out DIR`.
8. Test: parse response, `fit_image`, lỗi quota, secret thiếu; transport giả lập bằng
   `httpx.MockTransport`. Test `live` cho từng provider khi có secret.
9. Smoke test (ghi report): REST trên free plan, số neuron và thời gian mỗi ảnh 1024×576, chất
   lượng 3 prompt mẫu theo segment type, kết quả sau `fit_image` lên 1920×1080.

## Verification

- `uv run pytest tests/adapters -m "not live"` pass; conformance pass cho cả hai provider.
- `factory media check image --profile live` tạo PNG 1920×1080.
- Người dùng đã đọc điều khoản BFL trước ảnh thật đầu tiên (ghi vào report).
