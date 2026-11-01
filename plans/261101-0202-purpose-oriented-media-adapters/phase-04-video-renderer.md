---
phase: 4
title: "Video renderer và đo thời gian render"
status: completed
priority: P2
effort: "0.5d"
dependencies: [1]
---

# Phase 4: Video renderer và đo thời gian render

## Goal

Render đi qua `VideoRenderer`; FFmpeg + Pillow là implementation `ffmpeg_pillow`, nên Remotion sau
này chỉ là thêm một provider. Đo thời gian render một episode 5 phút trên laptop.

## Files to Create / Modify

- Modify: `factory/adapters/video/ffmpeg_pillow.py` (code từ `factory/workers/render.py`)
- Modify hoặc xóa: `factory/workers/render.py` (chỉ còn phần không phụ thuộc renderer, nếu có)
- Modify: `factory/orchestrator/stations.py` (`c8_render` lấy `identity` từ renderer; identity gồm `ffmpeg.version()` và phiên bản Pillow như hiện nay)
- Modify: `factory/cli.py` (`factory media check video --props FILE`)
- Modify: `tests/test_workers.py`, conformance video

## Tasks & Steps

1. Chuyển `wrap`, `caption_frame`, `render` sang `ffmpeg_pillow.py`, giữ output bit-exact.
2. Font: dùng font của pack (`pack.fonts`) nếu có file trong config, không có thì font mặc định
   của Pillow như hiện nay; giữ nguyên hành vi, không đổi thiết kế khung hình.
3. `factory media check video` render một `RenderProps` có sẵn từ artifact store và in thời gian.
4. Smoke test: dựng `RenderProps` 5 phút (khoảng 80 caption) từ fake audio/image, đo thời gian và
   kích thước file, ghi vào report.

## Verification

- Conformance video pass; `scripts/ci.sh` pass và hash `master.mp4` của episode xx-fixture không đổi
  so với trước khi chuyển (render bit-exact).
- Report có thời gian render 5 phút.
