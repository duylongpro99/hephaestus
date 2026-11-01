---
title: "Azure Speech: retry, duration, billing, rate range"
status: completed
priority: P1
effort: 0.5d
---

# Phase 1: Azure Speech: retry, duration, billing, rate range

## Context

- `factory/adapters/speech/azure_speech.py`, `factory/adapters/speech/base.py`, `factory/adapters/speech/fake.py`
- `factory/adapters/media.py` (dựng `AzureSpeech` từ `provider.options`), `config/media.yaml`
- `tests/adapters/test_azure_speech.py` (SDK giả), `tests/adapters/conformance.py`
- Mục 3, 6, 7 và phần adapter của mục 8 trong [plan](./plan.md).

## Hiện trạng (đã đọc code)

- Vòng retry chỉ xử lý `CancellationErrorCode.TooManyRequests`. SDK đã cài có thêm `ServiceTimeout`,
  `ConnectionFailure`, `ServiceUnavailable`, `ServiceError`, `ServiceRedirectTemporary`, … Lỗi tạm thời
  hiện làm hỏng cả station, và runner retry toàn bộ station.
- `duration = result.audio_duration.total_seconds()`, sau đó dùng để kẹp `end_s` của word timing.
- `charge(self.name, voice_id, len(request.text), self.price)`.
- `ssml()` kẹp rate vào `[0.5, 2.0]` mà không báo.

## Requirements

1. **Retry lỗi tạm thời.** Retry `ServiceTimeout`, `ConnectionFailure` và `ServiceUnavailable` với
   exponential backoff (2, 4, 8 s, có trần), dùng chung ngân sách `RETRIES` với throttling. Throttling
   vẫn chờ theo `retry-after`. Các lỗi khác (`AuthenticationFailure`, `Forbidden`, `BadRequest`, …)
   báo lỗi ngay, không retry.
2. **Không tính phí lần thất bại.** Chỉ tạo `Charge` sau lần thành công, nên `charges` luôn có đúng
   một phần tử dù đã retry.
3. **Duration từ WAV.** Sau khi ghi `out_path`, mở bằng `wave` và tính `nframes / framerate`. Nếu
   `framerate` khác `self.sample_rate` hoặc không phải mono 16-bit thì báo `SpeechError`. Kẹp word
   timing theo duration này.
4. **Billing ký tự wide.** Thêm option `wide_char_units` (mặc định 1) vào provider `azure-speech`
   trong `config/media.yaml`, đặt là `2`. Số unit được tính bằng
   `sum(wide if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)`. Hàm này đặt
   trong `factory/adapters/costs.py` (`billed_chars(text, wide_units)`) để provider khác dùng lại. Không có
   nhánh nào theo mã ngôn ngữ.
5. **Khai báo rate range.** Protocol `SpeechSynthesizer` có thêm `rate_range: tuple[float, float]`.
   Azure là `(0.5, 2.0)`; fake speech là `(0.25, 4.0)` hoặc khoảng hiện tại của fake. `ssml()` không
   kẹp nữa: rate ngoài khoảng thì báo `SpeechError` (worker sẽ kiểm tra trước ở phase 2, đây là lớp
   bảo vệ thứ hai).

## Related code files

- Sửa: `factory/adapters/speech/azure_speech.py`, `factory/adapters/speech/base.py`,
  `factory/adapters/speech/fake.py`, `factory/adapters/costs.py`, `factory/adapters/media.py`,
  `config/media.yaml`
- Sửa test: `tests/adapters/test_azure_speech.py`, `tests/adapters/conformance.py`,
  `tests/adapters/test_fake_providers.py` (nếu kiểm protocol)

## Implementation steps

1. Thêm `TRANSIENT = {ServiceTimeout, ConnectionFailure, ServiceUnavailable}` (tra bằng `getattr` trên
   `sdk.CancellationErrorCode` để SDK giả vẫn chạy) và `backoff_s(attempt)` có trần.
2. Viết lại vòng retry: throttled thì chờ `retry_after`, transient thì chờ `backoff_s`, còn lại raise.
   Hết lượt retry thì raise và nêu số lần đã thử.
3. Ghi WAV, rồi đọc lại bằng `wave` để lấy duration. Bỏ `audio_duration`.
4. Thêm `billed_chars()` vào `costs.py`. `AzureSpeech.__init__` nhận `wide_char_units: int = 1`;
   `media.py` đọc `provider.options.get("wide_char_units", 1)`.
5. Thêm `rate_range` vào protocol, Azure và fake. `ssml()` raise khi rate nằm ngoài khoảng.
6. Conformance: synthesizer phải có `rate_range` hợp lệ (`0 < lo < 1 < hi`), và `duration_s` khớp số
   frame của WAV (sai số ≤ 1 frame).

## Tests (mock, không mạng)

- `test_transient_cancellations_are_retried_with_backoff`: SDK giả trả `ServiceTimeout`, rồi
  `ConnectionFailure`, rồi thành công. Kết quả: `sleep` được gọi với 2 và 4, có đúng một `Charge`.
- `test_transient_cancellations_give_up_after_the_retry_budget`.
- `test_authentication_failure_is_not_retried`.
- `test_duration_is_counted_from_the_wav_frames`: SDK giả trả `audio_duration` lệch 0,3 s so với số
  frame thật. Kết quả `duration_s` theo số frame, và `end_s` cuối không vượt quá duration.
- `test_a_wav_at_the_wrong_sample_rate_is_refused`.
- `test_wide_characters_bill_at_the_configured_weight`: dùng chuỗi trộn ASCII và ký tự fullwidth/CJK
  (chỉ là dữ liệu test). `wide_char_units=2` cho unit đúng; mặc định 1 thì bằng `len(text)`.
- `test_a_rate_outside_the_provider_range_is_refused` (thay test kẹp hiện tại trong
  `test_ssml_sets_the_voice_locale_clamps_the_rate_and_escapes_the_text`).
- `test_the_live_profile_reads_wide_char_units` qua `media.py`.

## Todo

- [x] Retry transient có backoff, không tính phí lần lỗi
- [x] Duration từ frame WAV và kiểm định dạng
- [x] `billed_chars()` và option `wide_char_units` trong `media.yaml`
- [x] `rate_range` trong protocol, Azure, fake; bỏ kẹp âm thầm
- [x] Cập nhật conformance và test Azure

## Success criteria

- Test trên pass với SDK giả; `uv run pytest tests/adapters` pass.
- `station_version` của `c5_audio` đổi (vì source Azure và `base.py` đổi). Test xác nhận rằng sửa
  `wide_char_units` không đổi `identity`, vì giá không làm đổi audio.

## Risk

- Azure có thể tính phí cả request bị cancel. Ghi vào checklist smoke để kiểm; code giả định là không.
- `ServiceError` có thể là lỗi tạm thời hoặc lỗi cố định. Không retry để tránh tốn tiền; xem lại sau smoke.

## Security

Không đổi cách xử lý key. Test dùng key giả, không đọc `.env`.
