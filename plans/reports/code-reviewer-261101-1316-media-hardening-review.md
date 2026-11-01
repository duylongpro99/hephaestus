# Review: gia cố media adapter trước lần chạy live

Ngày: 2026-11-01. Plan: [media-hardening-before-live](../261101-1201-media-hardening-before-live/plan.md).
Phạm vi: `git diff` chưa commit (32 file) cùng migration `0003_cost_ledger_dedupe_key.sql`, `0004_publish_attempt.sql`.
Chỉ đọc. Có chạy một script tái hiện trong scratchpad, không sửa repo.

## Kết luận

Thiết kế marker upload đúng ở các điểm then chốt:

- Connection autocommit, runner không bọc station trong transaction. Vì vậy `UploadRecords.start`
  commit trước khi gửi byte nào, còn `finish` ghi receipt và xóa marker trong một transaction.
- Nhánh có marker không bao giờ gọi `publisher.upload`.
- `videos.insert` chỉ được gọi sau `find()`.

Phân loại `video_may_exist` đi theo hướng an toàn: lỗi lạ giữ marker. Ledger dedupe, retry Azure,
schedule idempotent và đếm tag đều đúng với plan.

Có **một bug correctness thật**: ledger tính thiếu khi hai dòng giống hệt nhau (đã tái hiện). Ngoài
ra có vài điểm vận hành cần sửa hoặc ghi rõ trước khi chạy live. Không thấy đường nào gọi
`videos.insert` khi còn marker trong luồng `factory run`. Ngoại lệ duy nhất là lệnh smoke
`factory media check publishing`, lệnh này đi vòng qua marker (finding 5).

Constraint: không có mã plan hay phase trong code, test hay migration. Không hard-code ngôn ngữ trong
`factory/`: `billed_chars` theo `east_asian_width`, hệ số lấy từ `media.yaml`. Không có fallback
provider. Test mới đều dùng SDK hoặc transport giả. Đã có backup DB (`backups/20261101-130554-…`,
`…-131113-…`) và `backups/` đã vào `.gitignore`.

## High

### 1. Hai dòng có cùng text, voice và rate chỉ được ghi ledger một lần (tính thiếu tiền thật)

`factory/workers/voice.py:73-76` (`line_key`), `:166` (`dedupe_key`)

- **Nguyên nhân:** `line_key` = sha256(identity, text, language, voice, rate) và không có `line_id`.
  Tên file vẫn có `line_id` (`line_paths`), nên hai dòng giống hệt nhau, ví dụ "Listen and repeat."
  hay một câu drill lặp lại (rất phổ biến trong video học ngoại ngữ), sẽ được **tổng hợp và tính phí
  hai lần**. Nhưng cả hai charge mang cùng `dedupe_key = c4_tts:<dir>:<key>`. `repo.add_costs` chèn
  dòng đầu, dòng sau bị `ON CONFLICT DO NOTHING` bỏ qua.
- **Tái hiện:** dùng `PricedSpeech` từ `tests/test_workers.py`, sửa text của dòng thứ hai có cùng
  voice và rate cho giống dòng một. Kết quả là `calls 4, entries 4, unique keys 3`: 4 request thật
  nhưng ledger chỉ ghi 3.
- **Hệ quả:** `spent_usd` thấp hơn thực tế, nên budget guard có thể không chặn kịp. Docstring nói
  "Two real syntheses with the same key … are charged once" chỉ cho trường hợp người vận hành xóa WAV.
  Còn đây là luồng bình thường.
- **Cách sửa:** thêm `d.line_id` vào `dedupe_key`, ví dụ
  `f"{STATION}:{media_dir.name}:{safe_name(d.line_id)}:{key}"`. Giữ `key` cho file. Thêm test có hai
  dòng trùng text.

## Medium

### 2. Lỗi mạng hoặc transport trước byte đầu tiên không được đổi thành `PublishError`, nên giữ marker và cần người vận hành xử lý

`factory/adapters/publishing/youtube.py:172-180` (`run` chỉ bắt `HttpError` và `RefreshError`), `:81`
(`creds.refresh`), `:146-150`, `:165-169`

- **Kịch bản:** mạng chập chờn đúng lúc upload. `find()` hoặc request khởi tạo session ném
  `httplib2.ServerNotFoundError`, `socket.timeout`, `ConnectionResetError` hoặc
  `google.auth.exceptions.TransportError` (lỗi khi `creds.refresh`). Đây không phải `PublishError`,
  nên `publisher.upload` (`factory/workers/publisher.py:89`) không xóa marker. Runner retry, đi vào
  nhánh marker, poll 3 lần (khoảng 2 phút) không thấy video rồi escalate.
- **Hệ quả:** an toàn (không có bản thứ hai) nhưng mỗi sự cố mạng tạm thời trước khi gửi byte đều
  dừng episode và bắt người vận hành chạy `publish resolve --not-uploaded`. Plan ghi "`find()` lỗi"
  thuộc loại `video_may_exist=False`, nhưng hiện chỉ đúng khi `find` lỗi HTTP.
- **Cách sửa:** trong `upload()`, bọc `find` và đoạn trước `next_chunk` để mọi `Exception` xảy ra khi
  `request.resumable_uri is None` đều thành `PublishError(video_may_exist=False)`. Một cách khác là
  để `run()` bắt thêm `OSError`, `httplib2.HttpLib2Error` và `google.auth.exceptions.TransportError`,
  còn `upload()` quyết định `video_may_exist` theo `resumable_uri` như hiện nay. Thêm test mock ném
  `TimeoutError` trong `find`.

### 3. Thông điệp lệnh `resolve` chỉ sang `factory run` cho episode ESCALATED, nhưng runner không chạy episode ESCALATED

`factory/cli.py:652`

- **Kịch bản:** `c10_upload` hết 3 lần thử vì lỗi trước byte đầu tiên, ví dụ quota upload hết. Marker
  được xóa sau mỗi lần thử và episode chuyển sang `ESCALATED`. Người vận hành chạy
  `factory publish resolve`, nhận câu "has no interrupted youtube upload; resume it with
  `factory run`". Nhưng `Runner._advance` trả về ngay khi `state in STOPPED`. Không có lệnh nào đưa
  episode này về `FINAL_APPROVED` ngoài sửa DB bằng tay.
- **Cách sửa:** sửa thông điệp, ví dụ "nothing to resolve: no upload can be on the platform; the
  episode needs a resume, which the factory has no command for yet". Hoặc cho phép `--not-uploaded`
  khi không có marker, vì chuyển `ESCALATED → FINAL_APPROVED` ở `c10_upload` lúc này là an toàn:
  upload luôn gọi `find()` trước. Lệnh resume chung là non-goal, nhưng hướng dẫn sai thì phải sửa.

### 4. Azure: duration lấy từ header WAV, còn kiểm tra tái dùng đếm frame thực, nên hai cách đếm có thể lệch

`factory/adapters/speech/azure_speech.py:138-149` (`wav.getnframes()` là số frame theo header),
`factory/workers/voice.py:99-102` (`len(readframes(...)) // frame_size` là số frame thực)

- **Kịch bản:** nếu `audio_data` của Azure có kích thước chunk `data` trong header không khớp dữ liệu
  (placeholder 0 hoặc `0xFFFFFFFF` như một số định dạng streaming), `wav_seconds` trả 0 hoặc một số
  rất lớn. Khi đó sidecar ghi duration sai và `load_line` luôn thấy lệch, nên **mọi lần retry tổng hợp
  lại mọi dòng và trả tiền lại**. Manifest và composer cũng nhận duration sai.
- Mục smoke "Chênh lệch giữa `audio_duration` và số frame WAV" đã có, nhưng code chưa tự bảo vệ.
- **Cách sửa:** `wav_seconds` đếm frame thực như `load_line`, hoặc báo `SpeechError` khi
  `getnframes()` khác số frame đọc được. Dùng chung một helper cho cả hai nơi để tránh hai định nghĩa
  "duration" khác nhau.

## Low

### 5. `factory media check publishing` gọi `upload()` trực tiếp, đi vòng qua marker

`factory/cli.py:578`. Report smoke chạy lệnh này hai lần liên tiếp với cùng package. Nếu package lấy
từ một episode thật đang có marker (người vận hành điều tra một escalation), lệnh có thể tạo bản thứ
hai khi playlist uploads chưa cập nhật. Đây là công cụ smoke trên kênh staging. Nên ghi cảnh báo
trong help hoặc report smoke: chỉ dùng package của episode không chạy qua orchestrator. Một cách khác
là từ chối khi DB có marker cho `episode_id` đó.

### 6. `resolve --external-id` chấp nhận video thiếu tag `ep-<id>` mà chỉ cảnh báo

`factory/cli.py:667`. Gõ nhầm id của episode khác thì hai receipt trỏ cùng một video, và
`c10_schedule` sẽ đặt lại `publishAt` của video kia. Plan cho phép cảnh báo, nhưng nên yêu cầu thêm
`--force` khi tag không khớp. Đây là quyết định của người dùng, cần hỏi lại trước khi đổi.

### 7. Ledger vẫn có thể mất phí một dòng khi crash giữa `os.replace(wav)` và ghi sidecar

`factory/workers/voice.py` (`store_line`). Lần sau không thấy sidecar nên tổng hợp lại. Charge của
lần đầu không bao giờ được ghi. Khe này rất hẹp và ledger vẫn là mức sàn. Chỉ cần ghi vào docstring
cùng chỗ đã nói về trường hợp xóa WAV bằng tay.

### 8. `ExportPublisher.find` đọc meta không atomic

`factory/adapters/publishing/export.py:32-36`, `:51`. Nếu crash giữa lúc `write_text` ghi meta,
`json.loads` ném `JSONDecodeError` trong nhánh marker, nên mọi lần retry đều lỗi rồi escalate. Chỉ
ảnh hưởng profile `fake`/export. Nên ghi meta qua file tạm rồi `os.replace` như `ArtifactStore.write`.

### 9. `station_version` của compliance không theo `publishing/base.py`

`factory/orchestrator/stations.py:352`. `compliance.check` giờ phụ thuộc `upload_tags` và
`episode_tag` trong `factory/adapters/publishing/base.py`, nhưng version chỉ hash
`source(compliance)`. Nếu đổi format tag, report compliance cũ vẫn được dùng lại. Nên thêm
`source(publishing_base)`.

## Đã kiểm, không thấy lỗi

- **Đường gọi `videos.insert`:** chỉ có `YouTubePublisher.upload`. Hàm này được gọi từ
  `workers/publisher.upload` (nhánh không có receipt và không có marker, sau `records.start` đã
  commit) và từ `cli media check publishing` (finding 5). Nhánh marker chỉ gọi `find`.
  `resolve --not-uploaded` xóa marker rồi chuyển về `FINAL_APPROVED`. Lần upload sau vẫn gọi
  `find()` trước `insert`.
- **Transaction:** `db.connect` dùng autocommit. Runner chỉ mở `transaction()` để ghi job, artifact
  và cost sau khi station xong, nên `start`, `clear` và `finish` đều commit độc lập. `finish` lỗi
  (DB rớt) sau khi upload xong thì marker còn, nên retry tìm lại video. Không có upload thứ hai.
- **`video_may_exist=False`:** chỉ đặt khi `find` lỗi `PublishError`, khi `MediaFileUpload` lỗi
  `OSError`, hoặc khi `next_chunk` lỗi lúc `resumable_uri is None`. Cả ba đều xảy ra trước khi có
  session upload, nên không thể có video.
- **CLI `resolve` chạy song song:** `move_unchecked` có `WHERE status = ESCALATED`, và
  `publish_receipt` có PK, nên lần chạy thứ hai rollback.
- **Migration:** `ON CONFLICT (episode, dedupe_key) WHERE dedupe_key IS NOT NULL` khớp đúng partial
  unique index. Entry không có key vẫn cộng dồn. `publish_attempt` có FK tới `episode`.
- **Azure retry:** `limiter.wait()` chạy ở mỗi lần thử, `events` tạo mới ở mỗi lần `speak`, nên
  không bị nhân đôi word boundary. `ServiceError` không retry. Chỉ request thành công mới có charge.
- **Schedule:** chỉ bỏ qua khi `status == "scheduled"` và `publish_at` trùng. So sánh datetime
  tz-aware theo thời điểm nên không phụ thuộc timezone của session.
- **Hash `master.mp4`:** không đổi, theo xác nhận của lead. Test
  `test_the_voice_station_version_follows_the_worker_and_adapter_source` có mặt.

## Việc nên làm (theo thứ tự)

1. Sửa finding 1 (thêm `line_id` vào `dedupe_key`) và thêm test dòng trùng. Đây là bug duy nhất làm
   sai số tiền.
2. Sửa finding 2 để lỗi mạng trước session không bắt người vận hành can thiệp.
3. Sửa thông điệp ở finding 3, hoặc cho `--not-uploaded` chạy khi không có marker (cần người dùng
   quyết).
4. Finding 4: thống nhất cách đếm frame, hoặc ít nhất đưa vào checklist smoke như điều kiện chặn.
5. Các mục Low thì tùy chọn.

## Câu hỏi chưa giải quyết

- Có muốn `resolve --external-id` bắt buộc `--force` khi tag không khớp (finding 6) không? Hiện plan
  chỉ yêu cầu cảnh báo.
- Có muốn mở rộng `--not-uploaded` cho episode escalated ở `c10_upload` mà không có marker không
  (finding 3)? Việc này chạm tới non-goal "lệnh resume chung".
