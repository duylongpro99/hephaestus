---
phase: 2
title: "Speech: Azure và smoke test giọng"
status: in-progress
priority: P1
effort: "1.5d"
dependencies: [1]
---

# Phase 2: Speech: Azure và smoke test giọng

## Goal

`azure_speech` là một implementation của `SpeechSynthesizer`, pass bộ conformance và trả lời
được ba câu hỏi smoke test của ADR 0003 về giọng.

## Files to Create / Modify

- Create: `factory/adapters/speech/azure_speech.py`
- Modify: `config/media.yaml` (provider `azure-speech`, profile `live.speech`, giá S0)
- Modify: `factory/cli.py` (nhóm lệnh `factory media`: `voices`, `check`)
- Modify: `pyproject.toml` (`azure-cognitiveservices-speech`), `.env.example`
- Create: `tests/adapters/test_azure_speech.py`
- Create: `plans/reports/smoke-<date>-media-providers.md` (report dùng chung cho phase 2, 3, 4, 5)

## Tasks & Steps

1. Provider config: `{type: azure_speech, api_key_env: AZURE_SPEECH_KEY, region_env: AZURE_SPEECH_REGION}`.
   Profile `live.speech`: `voices: {en-gb-female-1: en-GB-SoniaNeural, en-gb-male-1: en-GB-RyanNeural}`
   (giọng cụ thể chốt sau khi nghe ở bước 6), `sample_rate: 24000`.
2. Dựng SSML từ `SpeechRequest`: `xml:lang` theo locale của giọng, `<prosody rate="{rate:.2f}">`
   kẹp trong 0.5–2.0, escape XML cho `text`. Output format `Riff24Khz16BitMonoPcm` để WAV ghép
   được bằng `voice.assemble` không cần chuyển đổi.
3. Dùng Speech SDK `SpeechSynthesizer` với `synthesis_word_boundary` để gom `WordTiming`
   (offset đơn vị 100 ns). Không có event nào thì `words=None`.
4. Lỗi và giới hạn: `ResultReason.Canceled` thành `SpeechError` có lý do; HTTP 429 thì chờ theo
   `Retry-After` và thử lại tối đa 3 lần; client tự giãn để không quá 20 request/60 s (giới hạn F0, đặt trong config `max_requests_per_minute`).
5. Chi phí: `CostEntry(vendor=provider name, model=voice id, usd=chars * price)`; giá S0 lấy từ
   `prices` (cần kiểm trên Azure portal, ADR 0003).
6. Lệnh:
   - `factory media voices --profile live` in bảng key giọng → id provider.
   - `factory media check speech --profile live [--voice KEY] [--rate R] --text "..." --out DIR`
     tổng hợp một câu, in thời lượng, số word timing, chi phí, đường dẫn WAV.
7. Test: SSML builder, quy đổi offset, retry 429, map key giọng thiếu; SDK được inject (như
   `client=` của LLM router). Một test `live` gọi thật khi có `AZURE_SPEECH_KEY`, chạy bộ conformance.
8. Smoke test trên resource F0, ghi vào report:
   - `WordBoundary` có về trên F0 không.
   - Nghe câu mẫu A2 ở `rate` chậm của band (`band.rate.min / native_rate`) và tốc độ tự nhiên
     cho 2–3 giọng en-GB mỗi giới; người dùng chọn giọng cho Anna và Ben.
   - Thời gian cho 80 câu khi bị throttle.

## Verification

- `uv run pytest tests/adapters -m "not live"` pass.
- `uv run pytest -m live tests/adapters/test_azure_speech.py` pass trên F0.
- Report smoke test có kết quả cho ba mục trên và giọng được chọn đã ghi vào `config/media.yaml`.

## Risk

- F0 không có `WordBoundary`: giữ `words=None`, ghi vào report, đề xuất aligner ở plan sau.
- Speech SDK cần thư viện native trên macOS/Linux; ghi lỗi cài đặt (nếu có) vào report.
