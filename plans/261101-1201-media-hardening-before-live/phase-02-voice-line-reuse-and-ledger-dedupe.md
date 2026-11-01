---
title: "Voice: dùng lại WAV và ledger dedupe"
status: completed
priority: P1
effort: 1d
---

# Phase 2: Voice: dùng lại WAV và ledger dedupe

## Context

- `factory/workers/voice.py` (`voice()`), `factory/orchestrator/stations.py` (`voice_lines`)
- `factory/adapters/costs.py` (`Charge`, `ledger_entries`, `MediaError.costs`)
- `factory/contracts/cost_ledger.py` (`CostEntry`) và schema JSON trong `factory/contracts/schemas/`
- `factory/orchestrator/repo.py` (`add_costs`), `factory/orchestrator/runner.py` (`_run_step`)
- `factory/orchestrator/migrations/` (hiện có `0001`, `0002`)
- `tests/test_workers.py`, `tests/test_runner.py`, `tests/test_db.py`
- Mục 2 và phần worker của mục 8 trong [plan](./plan.md). Phụ thuộc vào `rate_range` từ phase 1.

## Hiện trạng (đã đọc code)

- Media dir của `c5_audio` là `path.with_suffix("")` của envelope, với
  `digest = artifact_hash(inputs, station_version)`. Retry cùng input và version sẽ ghi vào **cùng
  thư mục**, nên WAV của lần trước vẫn còn, nhưng `voice()` vẫn tổng hợp lại mọi dòng.
- Khi lỗi giữa chừng, `exc.costs = ledger_entries(STATION, charges)` và runner ghi các chi phí đó.
  Khi thành công, chi phí nằm trong envelope và được ghi khi `insert_artifact` trả về True.
- Nếu bỏ qua dòng đã có WAV:
  - Ghi chi phí của dòng dùng lại vào envelope thì bị tính hai lần (lần lỗi và lần thành công).
  - Không ghi thì mất chi phí khi process bị kill (không có exception, nên `exc.costs` không được ghi).
  - Người dùng chọn cách dùng khóa dedupe theo dòng.

## Requirements

1. **File dòng content-addressed.** Mỗi dòng ghi vào
   `lines/<safe line id>.<key12>.wav`, với `key = sha256(speech.identity, text, language, voice, rate)`.
   Kèm sidecar `.json` chứa `{key, duration_s, words, charges}`. WAV ghi qua file tạm rồi
   `os.replace`. Sidecar ghi sau cùng, cũng atomic, và đóng vai trò dấu "đã xong".
2. **Dùng lại.** Dòng được coi là hợp lệ khi sidecar đọc được, `key` khớp, WAV mở được bằng `wave`, và
   số frame khớp `duration_s` (sai số ≤ 1 frame). Khi đó dùng lại, không gọi provider. Dòng không hợp
   lệ thì xóa cả hai file rồi tổng hợp lại.
3. **Ledger dedupe.** `Charge` và `CostEntry` có thêm field tùy chọn `dedupe_key: str | None = None`.
   Charge của mỗi dòng có `dedupe_key = f"{STATION}:{key}"`. `ledger_entries` giữ riêng từng entry có key
   (không gộp), và vẫn gộp theo vendor/model cho entry không có key như hiện nay.
   Envelope `c5_audio` ghi chi phí của **mọi** dòng, kể cả dòng dùng lại, lấy từ sidecar. Khi lỗi,
   `exc.costs` chỉ gồm các dòng đã xong.
4. **Migration `0003_cost_ledger_dedupe_key.sql`.** Thêm cột `dedupe_key text NULL` và
   `CREATE UNIQUE INDEX ... ON cost_ledger (episode, dedupe_key) WHERE dedupe_key IS NOT NULL`.
   `repo.add_costs` chèn với `ON CONFLICT (episode, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING`.
   Entry không có key (LLM, image, …) vẫn chèn như cũ.
5. **Kiểm tra rate trước.** Trước khi tổng hợp dòng đầu tiên, `voice()` kiểm tra mọi request theo
   `speech.rate_range`. Có dòng ngoài khoảng thì raise `RateOutOfRange(SpeechError)` liệt kê các dòng và rate, khi đó
   `costs` rỗng. Lỗi này là lỗi cấu hình (band rate hoặc native rate của pack), nên station escalate
   thay vì retry 3 lần: `voice_lines` bắt lỗi này và trả `StationResult("escalate", ...)`.
6. **Hệ quả cho `station_version`.** Tên file và URI trong manifest đổi, nhưng `station_version` của
   `c5_audio` đã đổi vì source `voice.py` đổi. Cần có test xác nhận điều này.

## Related code files

- Tạo: `factory/orchestrator/migrations/0003_cost_ledger_dedupe_key.sql`
- Sửa: `factory/workers/voice.py`, `factory/adapters/costs.py`, `factory/contracts/cost_ledger.py`,
  `factory/contracts/schemas/cost_entry*.schema.json` (sinh lại theo cách repo đang làm),
  `factory/orchestrator/repo.py`, `factory/orchestrator/stations.py`
- Sửa test: `tests/test_workers.py`, `tests/test_runner.py`, `tests/test_db.py`, `tests/test_contracts.py`

## Implementation steps

1. Backup DB dev: `pg_dump "$DATABASE_URL" > backups/<timestamp>-before-cost-ledger-dedupe.sql`
   (không commit file backup).
2. Viết migration `0003` và cập nhật `add_costs`.
3. Thêm `dedupe_key` vào `CostEntry` (schema_version minor bump nếu contract có version), `Charge` và
   `ledger_entries`.
4. Trong `voice.py`: `line_key()`, `load_line()` (kiểm sidecar và WAV), `store_line()` (ghi tạm rồi đổi
   tên). Viết lại vòng lặp để dùng lại hoặc tổng hợp, và gom `charges` từ cả hai nguồn.
5. Thêm bước kiểm rate trước vòng lặp. `voice_lines` đổi lỗi rate thành escalate.
6. Kiểm tra lại `assemble()` vẫn nhận đúng danh sách path mới.

## Tests (mock, không mạng)

- `test_a_retry_reuses_lines_already_synthesized`: synthesizer giả lỗi ở dòng 3 lần đầu. Lần hai chỉ
  gọi provider cho dòng 3 trở đi; manifest giống hệt lần chạy không lỗi (trừ URI nếu khác).
- `test_a_line_with_a_truncated_wav_or_missing_sidecar_is_synthesized_again`.
- `test_a_changed_rate_or_voice_does_not_reuse_the_old_line` (key đổi).
- `test_the_envelope_lists_one_keyed_charge_per_line_including_reused_ones`.
- `test_a_rate_outside_the_synthesizer_range_fails_before_any_request` (synthesizer giả đếm số lần
  gọi bằng 0, `exc.costs == []`).
- DB (`-m db`): `test_keyed_costs_are_recorded_once`: ghi cùng key hai lần, `spent_usd` chỉ tính một lần;
  entry không key vẫn cộng dồn.
- Runner (`-m db`): `test_voice_retry_after_a_failure_charges_each_line_once`: lần 1 lỗi giữa chừng
  (runner ghi `exc.costs`), lần 2 thành công. Tổng ledger bằng tổng giá các dòng.
- Runner (`-m db`): `test_a_killed_voice_attempt_is_charged_when_the_retry_succeeds`: tạo sẵn WAV và
  sidecar như thể process chết trước khi kịp ghi ledger. Lần chạy sau ghi đủ chi phí của mọi dòng.
- `test_voice_station_version_changes_with_the_worker_source` (nếu chưa có test tương đương).

## Todo

- [x] Backup DB dev, migration `0003`, `add_costs` với ON CONFLICT
- [x] `dedupe_key` trong `CostEntry`, `Charge`, `ledger_entries` và schema JSON
- [x] File dòng content-addressed có sidecar, ghi atomic
- [x] Dùng lại dòng hợp lệ, tổng hợp lại dòng hỏng
- [x] Kiểm rate trước request đầu tiên, escalate khi sai cấu hình
- [x] Test worker, DB và runner

## Success criteria

- Retry station voice sau lỗi ở dòng k chỉ gọi provider cho các dòng từ k trở đi.
- Tổng `cost_ledger` của station `c4_tts` bằng đúng tổng phí các dòng, cả khi lỗi bằng exception lẫn
  khi process bị kill.
- `scripts/ci.sh` pass. Nếu hash audio hoặc video CI đổi thì ghi lý do; nội dung âm thanh không được đổi.

## Risk

- Hai lần tổng hợp thật với cùng key (ví dụ người vận hành xóa WAV bằng tay) chỉ được tính một lần.
  Ghi lại trong docstring; ledger vẫn là mức sàn như hiện nay với giá chưa có.
- File sidecar cũ không có `key` sẽ không hợp lệ, nên bị tổng hợp lại một lần. Chấp nhận được.

## Security

Sidecar chỉ chứa text của script, timing và chi phí. Không chứa secret.
