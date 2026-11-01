# Chọn provider thật cho TTS, image, render và publish

- **Ngày:** 2026-10-31 (mọi nguồn dưới đây được đọc ngày này, trừ khi ghi khác)
- **Phạm vi:** thay adapter giả (`factory/adapters/tts|image|publish`, `ffmpeg.py`) bằng vendor thật cho slice đầu `en` × adult × A2, support `en` + `vi`. Ưu tiên free tier hoặc chi phí gần 0, chấp nhận chất lượng thấp hơn lúc đầu.
- **Không thuộc phạm vi:** đăng ký dịch vụ, tạo key, sửa code, config hay ADR.
- **Ký hiệu:** ✅ đã đọc trên trang chính thức · ⚠️ chỉ có nguồn thứ ba, diễn đàn hoặc bản tóm tắt, cần kiểm tra lại · ❓ không xác minh được.

> **Revision 2026-10-31: không chạy model local.**
> Người dùng thêm ràng buộc: **không chạy inference model trên máy local**, vì không có phần cứng cho việc đó. Chỉ còn hosted API và managed endpoint. Tooling CPU thông thường vẫn được phép (FFmpeg encode, Pillow vẽ chữ, Remotion trên CPU).
>
> **Đã đổi:**
> - **TTS primary:** Kokoro local được thay bằng **Azure AI Speech S0**.
> - **TTS fallback:** Azure được thay bằng **Amazon Polly Neural** cho `en`. Kokoro chỉ còn ở dạng hosted (DeepInfra), là lựa chọn rẻ để cân nhắc.
> - **Alignment:** WhisperX local được thay bằng **Whisper hosted trên Cloudflare Workers AI**. Chỉ cần khi provider không trả timestamps.
> - **Image fallback:** "cùng model chạy local" được thay bằng **FLUX.2 [klein] 4B hosted trên DeepInfra**. Cùng model nên giữ được phong cách ảnh.
> - **Bổ sung:** điều khoản output của Cloudflare, lý do loại TTS của Cloudflare (MeloTTS, Aura), tải CPU của render, và cập nhật bảng rủi ro, quyết định và câu hỏi.
>
> **Hệ quả:** chi phí tối thiểu tăng từ ~$0 lên **~$3–5/tháng**. Không còn phương án TTS nào vừa miễn phí, vừa dùng thương mại rõ ràng, vừa có tốc độ chậm thật.
>
> **Bổ sung cùng ngày:** ghi lại quyết định của người dùng cho production, và thêm section "Provider cho môi trường testing (dev/staging)". Testing được dùng free tier phi thương mại, vì output không bao giờ publish công khai.

## Tóm tắt

Chạy cả bốn nhóm chỉ bằng hosted API tốn **khoảng $3–5/tháng** ở mức 30 tập × 5 phút. Gần như toàn bộ số tiền này là TTS.

| Nhóm | Primary | Fallback | Upgrade path | Chi phí/tháng (30 tập × ~5 phút) |
|---|---|---|---|---|
| TTS | **Azure AI Speech S0** (Neural, có `vi-VN`) | **Amazon Polly Neural** (chỉ `en`) | Azure Neural HD (DragonHD), sau đó ElevenLabs v3 | Azure ≈ $2.4 (`en`), ≈ $3.6 nếu đọc cả `vi` ⚠️ · Polly ≈ $2.4 ✅ · HD ≈ $3.3–5 ⚠️ · ElevenLabs $22–99 ✅ |
| Alignment (chỉ khi cần) | **Whisper large-v3-turbo** trên Cloudflare Workers AI | Groq `whisper-large-v3-turbo` | Deepgram Nova-3 | $0 trong free neurons · Groq ≈ $0.10 · Deepgram ≈ $0.65 (trừ vào $200 credit) |
| Image | **FLUX.2 [klein] 4B** trên Cloudflare Workers AI (free 10K neurons/ngày) | **FLUX.2 [klein] 4B** trên DeepInfra (cùng model) | Gemini image (Nano Banana 2) hoặc BFL API | $0 (≈$0.3 nếu vượt free) · fallback ≈ $2.4 · upgrade ≈ $20 |
| Render | **FFmpeg + Python**, chữ và phụ đề vẽ bằng Pillow thành PNG rồi overlay (CPU) | Remotion local trên CPU (Free License) | Remotion Company License / Lambda khi team > 3 người | $0 · upgrade $25/seat/tháng |
| Publish | **YouTube Data API v3** | Upload tay trong YouTube Studio từ gói export | Audit để nâng quota; podcast RSS (Spotify, YouTube) | $0 |

Bốn điểm cần biết trước khi đọc chi tiết:

1. **Không có TTS hosted nào vừa miễn phí vừa dùng thương mại được rõ ràng.**
   - ElevenLabs Free chỉ cho dùng phi thương mại ✅.
   - Theo moderator trên Microsoft Q&A, Azure F0 "does not carry those output use rights" cho mục đích thương mại ⚠️. Product Terms chính thức không đọc được.
   - Free tier của Polly là 12 tháng và không rõ còn áp dụng cho tài khoản AWS mới (gói credit từ 2025-07-15) ❓.
   - TTS của Cloudflare (MeloTTS, Aura) không có tham số tốc độ, nên không đạt yêu cầu "chậm thật" ✅.
   - Vì vậy primary là gói trả phí rẻ nhất có `vi-VN`, `prosody rate` và word timestamps.
2. **Quota YouTube đã thay đổi lớn.** Từ 2026-06-01, `videos.insert` có bucket riêng: 100 lần/ngày, 1 unit mỗi lần ✅. Bảng quota trong `docs/architecture.md` (1,600 unit cho mỗi upload, 3–4 tập/ngày) đã cũ. Mỗi tập giờ tốn khoảng 950 unit trong bucket 10K, tức khoảng 10 tập/ngày.
3. **FFmpeg trên máy này không vẽ được chữ.** Bản Homebrew `ffmpeg 9.0.2` không có `libass`/`freetype`, nên không có filter `subtitles`, `ass` hay `drawtext` (đã kiểm tra bằng `ffmpeg -filters`). Phụ đề burned-in và thumbnail cần Pillow, một bản FFmpeg build lại, hoặc Remotion. Cả ba đều chạy trên CPU.
4. **Điều khoản Cloudflare Workers AI để quyền output cho người dùng** ("you retain all applicable intellectual property … in Inputs and Outputs") ✅. Đổi lại, người dùng phải tuân theo điều khoản của model bên thứ ba: với FLUX là BFL ToS, trang này chưa đọc ❓.

## Ước lượng khối lượng

- **Ký tự TTS:**
  - Một tập 5 phút ở A2, có replay chậm, chứa khoảng 600 từ được đọc, tức ~3,300 ký tự tiếng Anh.
  - 30 tập là ~100K ký tự. Nhân 1.5 cho synthesize lại khi sửa script: **~150K ký tự/tháng**.
  - Nếu các dòng `vi` cũng được đọc thành tiếng, cộng thêm khoảng 50%, tức ~225K.
- **Audio:** 150 phút/tháng. Alignment chỉ cần nếu TTS không trả timestamps.
- **Ảnh:** khoảng 8–10 ảnh minh họa cộng 1–3 nền thumbnail mỗi tập, tức **~300 ảnh/tháng**.
- **Máy local:** Apple M1 Pro, RAM 16 GB, Node 24, FFmpeg 9.0.2. Từ revision này, máy chỉ chạy orchestrator, gọi API, encode và vẽ chữ.

---

## 1. TTS

### Yêu cầu từ code

- Interface `TTSProvider.synthesize(text, voice, rate, out_path) -> seconds` nhận `rate` theo đơn vị của pack. Pack `en` dùng `wpm` với `native_rate = 150` (`packs/en/pack.py:35`). Vì vậy adapter phải đổi wpm sang hệ số tốc độ của vendor (SSML `prosody rate` hoặc tham số `speed`).
- A6 (`factory/workers/voice.py`) gán mỗi cast member một voice cố định và chọn `rate.min` cho dòng chậm. `pack.voices` của `en` hiện đang rỗng, nên cần thêm roster thật.
- Architecture §12 quy định **không tự động fallback giọng**. "Fallback" trong báo cáo này nghĩa là provider dự phòng khi primary không qua bài nghe thử, không phải chuyển giọng lúc runtime.
- Persona `Anna` là "teacher from Manchester". Nếu giữ chi tiết đó, giọng host nên là en-GB.
- **Ràng buộc mới:** chỉ hosted API. Gọi SDK của vendor từ máy local được phép, vì SDK chỉ là client mạng, không chạy model.

### So sánh (chỉ hosted)

| Provider | Free tier | Giá trả phí | Tốc độ chậm (synthesize lại) | Word timestamps | `vi` | Thương mại / YouTube |
|---|---|---|---|---|---|---|
| **Azure AI Speech** | F0: 0.5M ký tự/tháng ✅, 20 transaction/60 s, không có batch ✅ | Neural ≈ $15–16/1M, Neural HD ≈ $22/1M ⚠️ (trang chính thức hiển thị "$-") | ✅ SSML `<prosody rate>` từ 0.5 đến 2× | ✅ sự kiện `WordBoundary` trong Speech SDK (REST thì không thấy tài liệu) | ✅ `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural` ⚠️ | Paid được dùng thương mại ⚠️ (moderator Microsoft, 2023). **F0 không có quyền output thương mại** theo hai moderator năm 2026 ⚠️. AI Code of Conduct yêu cầu "disclose … the synthetic nature of generated voices" ✅ |
| **Amazon Polly** | Neural 1M ký tự/tháng, Standard 5M, Generative 100K, "for the first 12 months" ✅. Tài khoản mới từ 2025-07-15 dùng gói credit tới $200 trong 6 tháng ✅; allowance theo tháng có còn áp dụng không thì ❓ | Standard $4/1M, **Neural $16/1M**, Long-Form $100/1M, Generative $30/1M ✅ | ⚠️ `<prosody>` cho Neural là "Partial availability" ✅; attribute `rate` theo engine chưa đọc ❓ | ✅ speech marks loại word cho Neural, Long-form, Standard. Generative không được liệt kê ✅ | ❌ không có vi-VN ✅ | ✅ "your Polly output belongs to you"; được cache và phát lại không giới hạn ✅ |
| **Google Cloud TTS** (Chirp 3: HD, Neural2, WaveNet) | Hạn mức tháng ❓: trang Free Tier không liệt kê TTS ✅, trang giá bị cắt. Có $300 credit cho khách mới ✅ | Chirp 3 HD ~$30/1M, WaveNet ~$4/1M ⚠️ | Chirp: `speaking_rate` 0.25–2.0 ✅, nhưng trang voices nói không hỗ trợ ❓ | Chirp ❌ không có `<mark>`/timepoints ✅. Neural2/WaveNet: có `SSML_MARK` timepoints ⚠️ (chỉ ở mức `<mark>`, không theo từng từ) | ✅ Chirp có `vi-VN`. Neural2/WaveNet `vi-VN` ❓ | ⚠️ điều khoản AI chung: "Generated Output is Customer Data"; chưa rõ TTS có thuộc nhóm này không ❓ |
| **Kokoro-82M hosted** (DeepInfra) | Không có free credit; phải gắn thẻ hoặc trả trước ✅ | **$0.99/1M ký tự** ✅ (≈ $0.15/tháng) | ✅ `speed` 0.25–4 ✅; Kokoro đổi tốc độ bằng synthesize lại (đã đọc `model.py`) | ⚠️ có tùy chọn "Return Timestamps", format chưa kiểm ❓ | ❌ | Weights Apache-2.0 ✅. ToS DeepInfra: "Customer retains all intellectual property rights in … Customer Data" ✅; output có thuộc Customer Data không thì ❓ |
| Kokoro hosted (fal / Together / Replicate) | Không thấy free credit | fal $0.02/1K ký tự (= $20/1M) ✅; Together $4/1M ✅; Replicate ≈ $0.00058/run ✅ | fal "0.1x to 5.0x" ✅; Replicate ❓ | ❓ | ❌ | fal nhãn "Commercial use permitted" ✅ |
| **Cloudflare MeloTTS** | 10K neurons/ngày chung ✅ (≈536 phút audio/ngày, tự tính) | $0.0002/phút audio ✅ | ❌ **không có tham số speed** (schema chỉ có `prompt`, `lang`) ✅ | ❌ | ❓ không liệt kê | Trang không có link license ❓ |
| **Cloudflare Deepgram Aura-1 / Aura-2-en** | ≈ 7.3K / 3.7K ký tự/ngày (tự tính) | $0.015 / $0.030 mỗi 1K ký tự ✅ | ❌ **không có speed** ✅ | ❌ | ❌ | Theo deepgram.com/terms (chưa đọc ❓) |
| **ElevenLabs** | 10K credits/tháng, **chỉ phi thương mại** ✅ | Starter $6 (30K credits), Creator $22 (121K), Pro $99 (600K) ✅. API: Flash/Turbo $0.04/1K ký tự, v3 $0.08/1K ✅ | ✅ `voice_settings.speed` | ✅ endpoint `/with-timestamps` trả alignment theo ký tự | ✅ (v3, 70+ ngôn ngữ) | Gói trả phí được dùng thương mại ✅. ToS không yêu cầu attribution ✅ |
| **Gemini TTS** (`gemini-3.8-flash-tts`, ...) | "Free of charge" ⚠️, nhưng nội dung được dùng để cải thiện sản phẩm ✅ | $9/1M token audio đến 31/12/2026, **$18 từ 1/1/2027** ⚠️ | ⚠️ chỉ điều khiển bằng prompt (field `style`), không có tham số số | ❌ | ⚠️ tóm tắt nói có | Google không nhận quyền sở hữu output ✅ |

Đã loại vì vi phạm ràng buộc mới: Kokoro local, Piper, Chatterbox, WhisperX local.

### Khuyến nghị

- **Primary: Azure AI Speech S0, giọng Neural.**
  - Đây là provider hosted duy nhất thỏa cả bốn yêu cầu trong một dịch vụ:
    - voice cố định cho từng cast member;
    - tốc độ chậm thật bằng `prosody rate`;
    - word timestamps qua `WordBoundary`;
    - có giọng `vi-VN`.
  - Nhờ `WordBoundary`, C5 **không cần** bước alignment cho tiếng Anh lẫn tiếng Việt.
  - Giọng en-GB có `en-GB-Sonia`, `en-GB-Ryan`, `en-GB-Ada`, `en-GB-Ollie` và bản `:DragonHDLatestNeural` ⚠️. Như vậy giữ được bio Manchester của Anna.
  - Ở ~150K ký tự/tháng, chi phí khoảng $2.4. Đọc cả `vi` thì ~225K ký tự, khoảng $3.6 ⚠️ (giá từ nguồn thứ ba).
  - **F0 chỉ dùng cho dev và nghe thử, không dùng cho audio sẽ publish** ⚠️. Đây là cách đọc của moderator trên diễn đàn, chưa có văn bản chính thức.
  - Adapter phải dùng Speech SDK (WebSocket) để nhận `WordBoundary`. REST chỉ trả audio.
  - `identity` gợi ý: `azure/<region>/<voice>`.
  - **Lock-in thấp:** SSML là chuẩn W3C. Muốn đổi vendor thì giữ interface và thay roster voice.
- **Fallback: Amazon Polly Neural, chỉ cho `en`.**
  - Polly có giá chính thức ✅ ($16/1M, ≈ $2.4/tháng), speech marks theo từng từ cho Neural ✅, và quyền output rõ ràng ✅.
  - Giọng en-GB: Amy, Brian (Neural và Generative), Emma, Arthur (Neural) ✅.
  - Điểm yếu:
    - Không có `vi`. Nếu dùng Polly cho `en`, dòng `vi` vẫn cần Azure, hoặc Google Chirp 3 HD cộng alignment hosted.
    - `prosody rate` trên Neural chỉ "Partial availability". Phải đọc trang `prosody-tag` và nghe thử trước khi tin ❓.
- **Lựa chọn rẻ, cân nhắc thêm: Kokoro-82M trên DeepInfra** (khoảng $0.15/tháng).
  - Có `speed` thật và weights Apache.
  - Nhưng format timestamps chưa kiểm tra, không có `vi`, en-GB chỉ đạt grade B-, và phải gắn thẻ trả trước.
  - Đáng thử nếu host dùng giọng en-US và mục tiêu là chi phí gần 0.
- **Upgrade path:**
  - Bước 1: Azure Neural HD (DragonHD), khoảng $3.3–5/tháng ⚠️. Không cần đổi adapter, chỉ đổi voice id.
  - Bước 2: ElevenLabs v3 cho host khi có doanh thu. Cần gói Creator ($22) cộng phần vượt, hoặc Pro ($99) ✅. Mức credit cho mỗi ký tự theo model chưa xác minh ❓.
- **Không chọn:**
  - Cloudflare MeloTTS và Aura: không có tham số tốc độ. Muốn chậm thì phải time-stretch, mà yêu cầu cấm cách đó.
  - Gemini TTS: free tier đổi lấy dữ liệu, tốc độ chỉ điều khiển bằng prompt, không có timestamps, giá tăng gấp đôi từ 2027.
  - fal Kokoro: đắt hơn DeepInfra khoảng 20 lần cho cùng model.

### Alignment hosted (chỉ khi TTS không trả timestamps)

Với Azure primary thì phần này **không cần**. Phần này chỉ dùng khi chọn Google Chirp cho `vi`, hoặc khi timestamps của Kokoro trên DeepInfra không dùng được.

| Dịch vụ | Free | Giá | Word timestamps | `vi` | Ghi chú |
|---|---|---|---|---|---|
| **Cloudflare `@cf/openai/whisper-large-v3-turbo`** | 10K neurons/ngày dùng chung với ảnh ✅; 46.63 neurons/phút, tức ≈214 phút/ngày nếu chỉ dùng cho việc này (tự tính) | $0.0005/phút ✅ | ✅ `segments[].words[]` có `start`/`end` (theo `schema-output.json`, chưa chạy thử ❓) | ⚠️ có `language` dạng string tự do, không có enum | Có `initial_prompt` để đưa script vào làm ngữ cảnh ✅ |
| **Groq `whisper-large-v3-turbo`** | Giới hạn free plan ❓. Trang chỉ có giới hạn Developer plan: 20 RPM, 2K RPD, 7.2K giây audio/giờ ✅ | $0.04/giờ audio ✅ (≈ $0.10/tháng) | ✅ `timestamp_granularities` với `verbose_json` (ví dụ code lại ghi `json`, mâu thuẫn ✅) | "Multilingual" ❓ | File tối đa 25 MB ở free; tính tối thiểu 10 giây mỗi request ✅ |
| **Deepgram Nova-3** | $200 credit, không cần thẻ, không hết hạn ✅ | $0.0043/phút monolingual ✅ | ❓ không thấy trên trang giá | "60+ languages" ❓ | — |
| OpenAI `whisper-1` | — | Không tải được trang giá ❓ | ✅ chỉ `whisper-1` hỗ trợ `timestamp_granularities` | — | **Bị deprecate, shutdown 2027-02-26** ✅. Không chọn |

- Whisper là ASR, không phải forced alignment.
- Adapter phải map các từ Whisper nhận ra về đúng từ trong script đã biết (fuzzy match). Đây là code tất định, không cần model.
- Tiếng Việt có dấu thanh, nên tỷ lệ khớp cần đo bằng một mẫu thật trước khi dùng ❓.

### Disclosure và monetize

- **Trang YouTube "Disclosing use of GenAI content"** ✅:
  - Bắt buộc khai báo khi nội dung làm người thật có vẻ nói hay làm điều họ không làm, sửa cảnh quay thật, tạo cảnh thực tế chưa từng xảy ra, hoặc tạo nhạc là trọng tâm video.
  - Giọng dẫn TTS không có trong danh sách ví dụ.
  - Trang ghi: "Disclosing AI content alone won't limit a video's audience or impact its eligibility to earn money."
- **Thiết lập hiện tại đã an toàn.**
  - `packaging.py` luôn đặt `contains_synthetic_media=True`, và field `status.containsSyntheticMedia` có trong `videos.insert` ✅. Nên giữ nguyên.
  - Microsoft AI Code of Conduct (v4.0, 2026-05-01) yêu cầu "disclose … the synthetic nature of generated voices" ✅. Flag trên cộng một dòng trong mô tả video ("Voices are AI-generated") là đủ cho cả hai.
- **Rủi ro monetize thật nằm ở "inauthentic/reused content"** ✅, không nằm ở giọng AI.
  - Ví dụ, YouTube không cho monetize nội dung "exclusively features readings of other materials you did not originally create".
  - Script của mình là bản gốc, nên rủi ro này do Originality Gate xử lý.

---

## 2. Image (minh họa và nền thumbnail)

Interface `ImageProvider.generate(prompt, width, height, out_path)` khá đơn giản, nên provider nào trả PNG theo kích thước cũng dùng được.

| Model / Provider | License weights | Output thương mại | Chi phí | Ghi chú |
|---|---|---|---|---|
| **FLUX.2 [klein] 4B trên Cloudflare** | Apache-2.0 ✅ | Cloudflare: "you retain all applicable intellectual property … in Inputs and Outputs" ✅. Trang model trỏ tới BFL ToS (chưa đọc ❓) | 26.05 neurons mỗi tile 512² output + 5.37 mỗi tile input ✅. Ảnh 1024×576 khoảng 80 neurons, tức **~125 ảnh/ngày miễn phí** (tự tính) | Free plan khi hết neurons thì "further operations will fail" ✅, không tự tính tiền |
| **FLUX.2 [klein] 4B trên DeepInfra** | Apache-2.0 ✅ | ToS: khách hàng giữ quyền IP với Customer Data ✅ | $0.014 × (w/1024) × (h/1024) ✅. Ảnh 1024×576 ≈ $0.0079, 300 ảnh ≈ **$2.4** | Phải gắn thẻ ✅. Cùng model nên giữ phong cách ảnh |
| FLUX.1 [schnell] trên fal / Replicate / DeepInfra | Apache-2.0 ✅ "personal, scientific, and commercial purposes" | fal: "Commercial use" ✅; Replicate: README Apache ✅ | fal $0.003/MP làm tròn lên ✅; Replicate $3/1K ảnh ✅; DeepInfra $0.0005 × MP × steps ✅. 300 ảnh ≈ $0.9 | Rẻ nhất, nhưng model khác nên phong cách lệch |
| FLUX.1 [schnell] trên Cloudflare | Apache-2.0 ✅ | Như Cloudflare ở trên | 4.80 neurons/tile + 9.60 neurons/step ✅. ~190 ảnh/ngày (tự tính) | Phương án dự phòng trong cùng tài khoản |
| FLUX.1 [dev], FLUX.2 [klein] 9B | Non-commercial ✅ | — | — | **Loại** |
| SDXL base 1.0 | CreativeML OpenRAIL++-M ✅ | Model card ghi "research purposes only" ✅ | — | Mơ hồ, không nên chọn |
| Gemini image (Nano Banana 2, `gemini-3.1-flash-image`) | — | Google không nhận quyền sở hữu ✅ | $0.067/ảnh 1K, batch $0.034 ⚠️. **Không có free tier** ⚠️ | Mạnh về chỉnh sửa và giữ nhân vật nhất quán |
| BFL API | — | "full commercial usage rights" ✅ | $0.048/ảnh 768² (trang không nói của model nào) ⚠️ | — |
| Hugging Face Inference Providers | — | — | Tài khoản free: "Monthly Credits: None" ✅; PRO $2/tháng credit ✅ | Không phải free tier, không chọn |

Cloudflare Workers AI: free **10,000 neurons/ngày**, reset 00:00 UTC; Workers Paid tính phần vượt $0.011/1K neurons ✅. Trang giá không nói cách cộng tile với step, nên số ảnh/ngày ở trên là ước lượng. REST API gọi được từ máy ngoài với Account ID và API token, không cần deploy Worker ✅. Free plan dùng REST được là suy ra từ trang giá, chưa có trang nào nói thẳng ❓.

### Khuyến nghị

- **Primary: FLUX.2 [klein] 4B qua Cloudflare Workers AI** (không đổi).
  - Free tier đủ cho ~300 ảnh/tháng với dư địa lớn.
  - Quyền output thuộc người dùng ✅. Cần đọc BFL ToS trước khi dùng thật, vì Cloudflare bắt tuân theo điều khoản của model bên thứ ba ❓.
- **Fallback: cùng model trên DeepInfra** (thay cho "chạy local").
  - Dùng khi Cloudflare hết neurons, lỗi, hoặc đổi điều khoản.
  - Cùng weights nên ảnh giữ cùng phong cách, khoảng $2.4/tháng nếu toàn bộ ảnh chuyển sang đây.
  - Nếu cần rẻ hơn và chấp nhận lệch phong cách: FLUX.1 [schnell] trên fal (~$0.9/tháng).
- **Upgrade path: Gemini image (Nano Banana 2)**, khoảng $20/tháng cho 300 ảnh. Dùng khi cần giữ ngoại hình Anna/Ben nhất quán giữa các tập.
- **Quy tắc "không người thật, không IP":**
  - Các license Apache không tự áp quy tắc này. Phải chặn bằng code trong A11 và bằng prompt template: không tên người thật, không thương hiệu hay nhân vật có bản quyền.
  - Lưu prompt cùng asset theo §13.
  - Thumbnail: chữ phải do renderer vẽ (C12), không để model ảnh sinh chữ.

---

## 3. Render

Không lựa chọn nào dưới đây chạy model. Tất cả là encode và vẽ trên CPU, nên vẫn hợp lệ với ràng buộc mới.

| Lựa chọn | License / chi phí | Khớp với code hiện tại | Tải trên laptop (30 tập × 5 phút/tháng) | Rủi ro |
|---|---|---|---|---|
| **FFmpeg + Python (Pillow vẽ chữ)** | LGPL/GPL tùy build, $0 | `ffmpeg.py` đã bit-exact và có test e2e | **Nhẹ.** Encode H.264 1080p, ảnh tĩnh cộng overlay PNG, ước tính 1–3 phút mỗi tập trên M1 Pro (chưa đo ❓). Pillow vẽ vài trăm PNG phụ đề mất vài giây. Có thể dùng `h264_videotoolbox` (encoder phần cứng, không phải model) nếu cần nhanh hơn, nhưng output sẽ không bit-exact | Không có libass/freetype trên máy này, nên phải vẽ phụ đề và karaoke thành PNG rồi `overlay`, hoặc cài bản FFmpeg có libass |
| **Remotion** (local, CPU) | Free cho "an individual", "a for-profit organization with up to 3 employees", và tổ chức phi lợi nhuận; dùng thương mại được ✅. Ngoài nhóm đó: Creators $25/seat/tháng; Automators $0.01/render, tối thiểu $100/tháng; Enterprise từ $500/tháng ✅ | Architecture đã thiết kế C7/C8/C12 bằng Remotion | **Vừa.** Headless Chrome chụp 9,000 frame (5 phút × 30 fps) mỗi tập. Ước tính 5–15 phút mỗi tập, RAM vài GB (chưa đo ❓). Một tập/ngày thì chạy được, nhưng máy sẽ nóng và chậm trong lúc render | Thêm toolchain TS. Output khó bit-exact. LICENSE ghi "In Remotion 5.0, the license will slightly change" ✅ ❓ |
| HyperFrames (HeyGen, HTML-first) | ❓ | Có skill sẵn trong môi trường | Tương tự Remotion ❓ | Chưa đánh giá license |

Trang giá Remotion không nói gói Automators có áp dụng cho render local hay không ❓.

### Khuyến nghị

- **Primary: giữ FFmpeg + Python cho slice đầu** (không đổi).
  - Video A2 dạng podcast chỉ cần ảnh nền, phụ đề hai ngôn ngữ, đánh dấu từ đang đọc và thanh tiến trình. Pillow vẽ các lớp này thành PNG theo timestamps, FFmpeg ghép lại.
  - Cách này nhẹ nhất cho laptop, giữ được tính bit-exact mà orchestrator dựa vào để cache, và không thêm runtime mới.
  - Thumbnail C12 cũng làm bằng Pillow. Font phải là OFL (§13).
- **Fallback: Remotion local trên CPU** theo Free License. Dùng khi layout hoặc animation vượt quá sức Pillow. Chấp nhận được ở 1 tập/ngày.
- **Upgrade path: Remotion Company License và Lambda** khi team vượt 3 người hoặc khi render local quá nặng. Lambda là render trên cloud, không phải inference.
- **Câu hỏi cần trả lời:** "employees" có tính cộng tác viên hoặc reviewer thuê ngoài không? LICENSE ghi "up to 3 employees", còn remotion.pro ghi "up to three people".

---

## 4. Publish

Không có model nào ở bước này. Khuyến nghị giữ nguyên.

### YouTube Data API v3 (theo trang chính thức, cập nhật 2026-10-15)

- **Quota mặc định:** 100 lệnh `videos.insert`/ngày (1 unit mỗi lệnh, bucket riêng từ 2026-06-01), 100 lệnh `search.list`/ngày, và 10,000 unit/ngày cho mọi endpoint khác. Reset lúc nửa đêm giờ PT ✅.
- **Chi phí trong bucket 10K:** `captions.insert` 400, `captions.update` 450, `thumbnails.set` 50, `videos.update` 50, `playlistItems.insert` 50 ✅.
- **Mỗi tập:** 2 caption (en, vi) + thumbnail + playlist + một lần update ≈ **950 unit**. Như vậy được khoảng 10 tập/ngày, trong khi nhu cầu là 1 tập/ngày.
- **Lịch sử thay đổi:** ngày 2025-12-04, chi phí upload giảm từ ~1,600 xuống ~100 unit; ngày 2026-06-01 tách bucket ✅. `docs/architecture.md` §12 và `docs/research.md` §4 cần cập nhật khi viết ADR.
- **Nâng quota:** điền form audit. Trang không nhắc phí ✅.
- **Project chưa audit:** có mâu thuẫn.
  - Revision history 2020-07-28: video upload từ project chưa verify tạo sau ngày đó "will be restricted to private viewing mode" ✅.
  - Trang `videos.insert` hiện tại: "Videos uploaded from unverified API projects are not restricted to private viewing mode" ✅.
  - Với pipeline `private` + `publishAt`, đây là rủi ro lớn nhất của nhóm publish. **Phải thử bằng kênh staging** trước khi tin vào lịch đăng tự động.
- **OAuth:** app External ở trạng thái "Testing" nhận refresh token **hết hạn sau 7 ngày** ✅. Như vậy phải đăng nhập lại mỗi tuần, nếu không runbook "OAuth refresh fails" sẽ dừng lane.
  - Để tránh, đưa app sang "In production". Cần xác minh `youtube.upload` có phải sensitive scope không ❓, và app chưa verify ở production bị giới hạn gì ❓.
  - Với một chủ kênh duy nhất, màn hình cảnh báo "unverified app" là chấp nhận được. Điều này chưa được xác nhận ❓.
- **Field cần thiết** có trong `videos.insert` ✅: `status.publishAt`, `status.containsSyntheticMedia`, `status.selfDeclaredMadeForKids`.

### Podcast RSS

- **YouTube RSS ingestion** ✅:
  - Chỉ có ở "select countries/regions"; Việt Nam có trong danh sách không thì chưa kiểm tra ❓.
  - Podcast phải là audio-first, xác minh quyền sở hữu qua email trong feed, và không có quảng cáo.
  - Tập đầu tiên lên ở chế độ private.
  - Trang không nói giá.
- **Hosting feed:** có thể tự host trên static hosting hoặc object storage, hoặc dùng dịch vụ podcast miễn phí. Chưa so sánh ❓.
- Dạng audio-only hợp với nội dung luyện nghe A2, nhưng là kênh phân phối thứ hai, không cần cho slice đầu.

### Khuyến nghị

- **Primary:** YouTube Data API v3 (miễn phí), app ở trạng thái production cho một người dùng.
- **Fallback:** adapter xuất gói (MP4, SRT/VTT, thumbnail, metadata JSON) để upload tay trong YouTube Studio. Cách này luôn hoạt động khi API bị khóa private hoặc OAuth hỏng.
- **Upgrade path:** làm audit để được nâng quota và gỡ mọi hạn chế với project chưa verify, sau đó thêm RSS cho Spotify/Apple/YouTube Music.

---

## 5. Provider cho môi trường testing (dev/staging)

**Phạm vi:** dev và staging được dùng free tier kể cả khi điều khoản cấm dùng thương mại. Output không bao giờ publish công khai; staging chỉ upload lên kênh YouTube private, không monetize. Vẫn chỉ dùng hosted API. Production giữ nguyên lựa chọn ở §1–§4.

**Kết luận:** dùng **Azure Speech F0 + Cloudflare Workers AI free + FFmpeg local + YouTube API vào kênh staging private**, chi phí $0. Đây là cấu hình gần production nhất:
- F0 dùng cùng giọng Neural, cùng SSML và cùng `WordBoundary` với S0.
- Cloudflare free chạy đúng model ảnh của production.

Nhờ vậy preview ở Gate 1 đại diện được cho production, trừ khi production dùng giọng HD.

### Tóm tắt

| Nhóm | Dev (chạy tay, smoke test) | Staging (episode đầy đủ, kênh private) | Giống production? | Giới hạn làm dừng một lần chạy |
|---|---|---|---|---|
| TTS | Azure F0 | Azure F0 (resource riêng, tách khỏi S0 của production) | ✅ cùng giọng Neural en-GB, cùng SSML `prosody rate` và `WordBoundary`. ❌ F0 không có Neural HD ✅ | 0.5M ký tự/tháng ✅ (≈150 tập 3.3K ký tự). **20 transaction/60 s, không nâng được** ✅: một tập ~80 dòng mất ≈4 phút nếu mỗi dòng là một request |
| Alignment | Không cần (có `WordBoundary`) | Không cần | — | — |
| Image | Cloudflare free, FLUX.2 [klein] 4B | Như dev | ✅ cùng model và cùng host | 10K neurons/ngày ✅ (≈125 ảnh, tức ≈12 tập/ngày, tự tính); 720 request/phút cho text-to-image ✅. Hết neurons thì request lỗi ✅ |
| Render | FFmpeg + Pillow local | Như dev | ✅ cùng code | CPU laptop; không có giới hạn ngoài |
| Publish | Không upload; adapter xuất gói | YouTube Data API v3, Google Cloud project riêng, kênh private | ✅ cùng API | 100 `videos.insert`/ngày và 10K unit/ngày cho mỗi project ✅ (≈10 tập/ngày) |

### TTS: xếp hạng free tier

| Hạng | Provider | Free allowance | Hợp nhu cầu (từng dòng, voice cố định, chậm thật, timestamps, en-GB) | Điều khoản cho testing | Giống production? |
|---|---|---|---|---|---|
| 1 | **Azure Speech F0** | 0.5M ký tự Neural/tháng ✅; 20 transaction/60 s, không nâng được ✅; 10 phút audio mỗi request ✅; không có batch, custom voice hay HD trên F0 ✅ | ✅ đủ cả năm. SDK/REST real-time có cột F0 ✅; `WordBoundary` trên F0 không được nêu riêng ❓ | Moderator: F0 dành cho "evaluation/testing" ⚠️ (trang chính thức không có câu này ❓). Không thấy yêu cầu attribution. Dùng dữ liệu để train: chưa đọc ❓ | **Có**, trừ giọng HD |
| 2 | **Amazon Polly** (AWS Free plan) | Tài khoản mới nhận $100 credit, kiếm thêm tối đa $100; tài khoản **tự đóng sau 6 tháng** hoặc khi hết credit ✅. Trang Polly vẫn ghi Standard 5M ký tự/tháng, Neural 1M/tháng trong 12 tháng, áp dụng cho cả Speech Marks ✅; hai cơ chế này kết hợp ra sao thì ❓ | ✅ en-GB Amy, Brian, Emma, Arthur ✅; word speech marks ✅; `prosody rate` trên Neural chỉ "Partial availability" ✅ | "your Polly output belongs to you" ✅; Polly có thể lưu và dùng text input để cải thiện dịch vụ, opt-out được ✅ | Không (vendor và giọng khác) |
| 3 | **Cartesia Free** | 20K credits/tháng, 1 credit/ký tự, ≈27 phút TTS ✅ | Speed, timestamps, en-GB không thấy ❓ | Commercial license chỉ có ở gói Pro (suy ra từ bảng) ⚠️ | Không |
| 4 | **ElevenLabs Free** | 10K credits/tháng, không rollover ✅; Flash/Turbo 0.5–1 credit/ký tự ✅ → khoảng **3 tập/tháng** | ✅ `speed`, `/with-timestamps`, voice library | Chỉ phi thương mại ✅; **bắt buộc dùng email cá nhân** khi dùng phi thương mại (§1(c)) ✅; tài khoản của bạn đang dùng email công ty, nên cần một tài khoản riêng. Mặc định dùng Content để train, opt-out được ✅. Attribution: không thấy. Bài help về upload YouTube trả 403 ❓ | Không |
| 5 | **Gemini TTS** (free tier) | Free ⚠️; RPM/RPD không công bố, chỉ xem được trong AI Studio ✅ | ❌ tốc độ chỉ điều khiển bằng prompt; ❌ không thấy timestamps; en-GB chọn qua `accent` ✅ | Unpaid: Google dùng input/output để cải thiện sản phẩm, có **human review** ✅. Phải ≥18 tuổi, dùng cho "professional or business purposes" ✅. Không cấm testing | Không |
| — | Google Cloud TTS | Free tháng ❓ (trang giá không đọc được); $300 credit dùng thử ✅ | en-GB có Neural2, WaveNet, Chirp 3 HD ⚠️; Chirp 3 HD không có SSML, không chỉnh được speaking rate ✅ | ❓ | Không |
| — | Deepgram ($200 credit, không cần thẻ ✅) | Credit có dùng cho Aura TTS không thì ❓ | ❌ Aura không có speed | ❓ | Không |
| — | Together, fal, DeepInfra, HF Inference Providers | **Không có free credit**: Together nạp tối thiểu $15 ✅; DeepInfra phải gắn thẻ ✅; fal không thấy ✅; HF free "None" ✅ | — | — | — |

### Image: xếp hạng free tier

| Hạng | Provider | Free allowance | Giống production? | Ghi chú |
|---|---|---|---|---|
| 1 | **Cloudflare Workers AI, FLUX.2 [klein] 4B** | 10K neurons/ngày, reset 00:00 UTC ✅; 720 rpm ✅ | **Có**: cùng model, cùng host | Không cần provider testing riêng. Nên dùng account hoặc token riêng cho staging để không ăn chung neurons với production ❓ (chưa đọc giới hạn số account) |
| 2 | Cloudflare FLUX.1 [schnell] | Dùng chung 10K neurons ✅ | Không (model khác) | Dự phòng khi muốn tiết kiệm neurons |
| 3 | HF ZeroGPU Spaces | 5 phút GPU/ngày cho tài khoản free ✅; chỉ Gradio ✅ | Tùy Space | Không có tài liệu cho việc gọi như API từ ngoài ❓. Không nên dựa vào |
| — | Replicate | "select models … for free, but after a bit you'll be asked to set up billing" ✅ | — | Không có allowance ổn định |
| — | Gemini image, Together, fal | Không có free tier ✅ | — | — |

### Alignment (chỉ khi TTS testing không có timestamps)

- **Cloudflare whisper-large-v3-turbo:** nằm trong 10K neurons/ngày ✅ và 720 rpm cho ASR ✅.
- **Groq:**
  - Có free plan, nhưng con số giới hạn riêng của free plan chưa tách được ❓. Developer plan là 20 RPM và 2K RPD ✅.
  - Services Agreement §4.2: "Groq is not permitted to use Inputs or Outputs for training" ✅.
- **Deepgram:** $200 credit, không hết hạn, không cần thẻ ✅. Khoảng 43,000 phút Nova-3 ✅.

### Khác biệt giữa testing và production

- **Giọng:**
  - Azure F0 và S0 dùng cùng giọng Neural, nên kết quả Gate 1 trên staging đại diện cho production.
  - Nếu sau này production nâng lên DragonHD, staging **không còn** đại diện về chất giọng, vì F0 không có HD ✅. Khi đó cần nghe thử HD trên S0 với vài dòng (chi phí không đáng kể).
  - Polly, ElevenLabs, Gemini và Cartesia cho ra giọng khác hẳn. Chỉ dùng để test pipeline (timing, format, lỗi), không dùng để duyệt chất giọng.
- **Ảnh:** Cloudflare free giống production 100%. Không có khác biệt.
- **Publish:**
  - Staging dùng Google Cloud project riêng, với quota 10K riêng.
  - Có thể để OAuth ở chế độ Testing. Refresh token 7 ngày chấp nhận được ở staging ✅.
  - Kênh private nên hạn chế "private lock" với project chưa audit không ảnh hưởng.
  - Chính kênh staging là nơi kiểm tra xem `publishAt` có hoạt động với project chưa audit không.

### Điều khoản cần lưu ý cho testing

- **Upload lên kênh YouTube private, không monetize:**
  - Không nhà cung cấp nào nói rõ trường hợp này ❓.
  - Với ElevenLabs Free và Azure F0, cách đọc hợp lý là private và không monetize thì vẫn là phi thương mại. Đây là suy luận, không phải tư vấn pháp lý.
- **Attribution:** không thấy yêu cầu ở Azure, ElevenLabs và Polly. Gemini chỉ "may require … attribution" theo luật hiện hành ✅.
- **Dùng dữ liệu để train:**
  - Gemini free: có, và có human review ✅. Không gửi script chưa phát hành nếu coi đó là bí mật.
  - ElevenLabs: có mặc định, opt-out được ✅.
  - Polly: có, opt-out qua AWS Organizations ✅.
  - Groq: không ✅.
  - Cloudflare: không dùng Customer Content để train ✅.
  - Azure F0: ❓.

### Khuyến nghị

- **Dev:**
  - Mặc định vẫn dùng adapter giả (`--fake-llm`, TTS/image giả) cho CI, như hiện tại.
  - Khi cần smoke test với vendor thật, gọi Azure F0 cho vài dòng và Cloudflare free cho vài ảnh. Chi phí $0.
- **Staging:**
  - Chạy một tập đầy đủ với Azure F0, Cloudflare free (account hoặc token riêng), FFmpeg + Pillow, và YouTube API vào kênh private trong Google Cloud project riêng. Chi phí $0.
  - Giới hạn thực tế là khoảng 10 tập/ngày, bị chặn bởi neurons và quota YouTube. Cộng thêm 4 phút throttle TTS cho mỗi tập.
- **Dự phòng TTS cho staging:** AWS Free plan (Polly), khi F0 hết 0.5M ký tự hoặc bị throttle. Chỉ dùng trong 6 tháng đầu của tài khoản.
- **Không khuyến nghị:**
  - ElevenLabs Free: chỉ khoảng 3 tập/tháng và cần email cá nhân.
  - Gemini TTS free: không có timestamps, không chỉnh được tốc độ thật, và dữ liệu bị dùng để train.

---

## Rủi ro và rào cản license

| # | Rủi ro | Mức | Giảm thiểu |
|---|---|---|---|
| 1 | Project YouTube chưa audit có thể bị khóa private, và video bị khóa không kháng cáo được (nguồn thứ ba) | Cao | Thử với kênh staging; nộp audit sớm; có fallback upload tay |
| 2 | Azure F0 không có quyền output thương mại (theo moderator diễn đàn); giá S0 chỉ có từ nguồn thứ ba | Trung bình | Chỉ dùng S0 cho audio sẽ publish; dùng F0 cho dev và nghe thử; kiểm tra giá trong Azure portal khi tạo resource |
| 3 | Refresh token 7 ngày ở chế độ Testing | Trung bình | Đưa app sang production; giữ bước re-auth trong runbook |
| 4 | Không còn TTS miễn phí dùng được cho publish: tối thiểu ~$2.4/tháng và cần thẻ thanh toán | Trung bình | Chấp nhận ~$3–5/tháng, hoặc thử Kokoro trên DeepInfra (~$0.15) nếu host dùng giọng en-US |
| 5 | Polly Neural: `prosody rate` chỉ "Partial availability", không có `vi` | Trung bình | Polly chỉ là fallback cho `en`; nghe thử dòng chậm trước khi dùng |
| 6 | Cloudflare bắt tuân theo điều khoản model bên thứ ba (BFL ToS chưa đọc); free plan hết neurons thì lỗi chứ không tự trả tiền | Trung bình | Đọc BFL ToS trước khi dùng thật; adapter coi lỗi quota là retryable, chuyển sang DeepInfra theo quyết định của người vận hành |
| 7 | Whisper hosted không phải forced alignment; khớp từ tiếng Việt chưa đo | Thấp (Azure đã có `WordBoundary`) | Chỉ dùng khi TTS không có timestamps; đo trên mẫu thật |
| 8 | FLUX.1 [dev], FLUX.2 [klein] 9B có license phi thương mại | Rào cản | Chặn trong licence register; chỉ cho phép model Apache-2.0 |
| 9 | OpenAI `whisper-1` shutdown 2027-02-26 | Thấp | Không chọn |
| 10 | Remotion 5.0 sẽ đổi license; "3 employees" và "three people" khác nhau; render Remotion trên CPU nặng hơn FFmpeg nhiều | Thấp | Chưa dùng Remotion; đọc lại khi bản 5.0 ra |
| 11 | Free tier của Cloudflare có thể thay đổi; Gemini TTS tăng giá 2027 | Thấp | Adapter có `identity` riêng; cùng model FLUX có ở nhiều host |
| 12 | FFmpeg local không có libass/freetype | Thấp | Vẽ bằng Pillow, hoặc ghi rõ yêu cầu build FFmpeg trong README/CI |
| 13 | Output testing tạo bằng free tier phi thương mại (Azure F0, ElevenLabs Free, Gemini free) lọt vào bản publish công khai | Trung bình | Người dùng đã quyết định không thêm code guard; tách resource, key và kênh giữa staging và production |
| 14 | Azure F0 throttle 20 transaction/60 s, không nâng được; không có giọng HD | Thấp | Chấp nhận thêm khoảng 4 phút mỗi tập ở staging; nghe thử HD trên S0 nếu production nâng cấp |
| 15 | AWS Free plan đóng tài khoản sau 6 tháng; ElevenLabs Free yêu cầu email cá nhân | Thấp | Polly chỉ là dự phòng ngắn hạn cho staging; không dùng ElevenLabs Free |

## Quyết định của người dùng (2026-10-31)

- **Production** theo khuyến nghị đã sửa: Azure S0 cho TTS, FLUX.2 [klein] 4B trên Cloudflare, FFmpeg + Pillow, YouTube Data API v3.
- **Giọng host:** en-GB.
- **Dòng `vi`:** slice đầu không đọc thành tiếng, chỉ hiện chữ trên màn hình.
- **Ngân sách production:** khoảng $3–5/tháng, có thẻ thanh toán.
- **Staging:** sẽ tạo một kênh YouTube private làm staging.
- **Remotion:** hoãn.
- **Dev và staging** được dùng free tier kể cả khi điều khoản cấm dùng thương mại (ví dụ ElevenLabs Free, Gemini free, Azure F0), vì output không bao giờ publish công khai. **Không thêm code guard** chặn output phi thương mại đi vào production.
- **Vẫn không chạy model local;** chỉ dùng hosted API.

## Quyết định còn mở (danh sách ban đầu, giữ để tham khảo)

Các mục 1, 2, 4, 5, 6 dưới đây đã có câu trả lời ở phần trên. Mục 3 (mô hình kinh doanh, quy mô team) vẫn còn mở.

1. **Giọng host (ADR 0001 quyết định 4):**
   - Giới tính và accent cho Anna và Ben: en-GB (khớp bio Manchester) hay en-US?
   - Ràng buộc mới làm cho en-GB không còn bất lợi về giá: Azure có nhiều giọng en-GB ở cùng mức giá. Chỉ khi chọn Kokoro hosted thì en-US mới tốt hơn rõ.
2. **Dòng `vi` có được đọc thành tiếng không**, hay chỉ hiện chữ trên màn hình?
   - Nếu đọc: Azure `vi-VN` (≈ +$1.2/tháng). Đây là lý do chính để Azure làm primary thay cho Polly.
   - Nếu chỉ hiện chữ: Polly và Azure ngang nhau về giá; Azure vẫn có lợi thế về giọng en-GB HD.
3. **Mô hình kinh doanh (ADR 0001 quyết định 5):**
   - Có monetize, tài trợ hay bán khóa học không? Nếu có, mọi free tier phi thương mại bị loại (ElevenLabs Free, Azure F0).
   - Team có vượt 3 người không? Quyết định này ảnh hưởng đến license Remotion.
4. **Mức chi tối đa mỗi tháng** cho giai đoạn chưa có doanh thu: ~$5 (Azure S0 + Cloudflare), hay ~$25 (thêm Gemini image hoặc HD voices).
   - Mức $0 không còn khả thi cho audio sẽ publish.
   - Cần một thẻ thanh toán cho Azure, và tùy chọn thêm cho DeepInfra.
5. **Có tạo Google Cloud project và kênh staging riêng** để thử chuyện khóa private và nộp audit sớm không?
6. **Render:** đồng ý giữ FFmpeg + Pillow cho slice đầu và hoãn Remotion (lệch với thiết kế C7/C8 trong architecture)? Ràng buộc "laptop thường" làm phương án này hợp lý hơn.

## Câu hỏi chưa giải quyết

- **Azure:**
  - Văn bản chính thức về quyền output của F0 so với paid: Product Terms (MCA, EAEAS) quá lớn để tải; câu trích trong bài hỏi trên diễn đàn chưa kiểm chứng.
  - Giá chính thức Neural và Neural HD: trang giá hiển thị "$-", Retail Prices API trả về rỗng.
- **Amazon Polly:**
  - Allowance tháng (1M Neural) có áp dụng cho tài khoản mới theo gói credit (từ 2025-07-15) không.
  - Chi tiết `prosody rate` cho Neural.
  - Customer Agreement chưa đọc.
- **Google Cloud TTS:**
  - Free tier tháng và bảng giá: trang giá bị cắt, trang Free Tier không liệt kê TTS, trang quotas trả 404.
  - Giọng `vi-VN` Neural2/WaveNet.
  - Loại giọng nào có timepoints.
- **Hosted Kokoro trên DeepInfra:**
  - Format timestamps.
  - Output có thuộc "Customer Data" trong ToS không.
- **Cloudflare:**
  - Nội dung BFL ToS (bfl.ai/legal/terms-of-service) và Deepgram terms.
  - License hiển thị cho MeloTTS và Whisper.
  - Free plan có gọi được REST API không: chỉ suy ra từ trang giá.
- **Alignment:**
  - Format `words[]` của Whisper trên Workers AI khi chạy thật.
  - Hỗ trợ `vi`.
  - Giới hạn free plan của Groq (trang chỉ có Developer plan).
  - Word timestamps của Deepgram.
- **Render:** tốc độ thật của FFmpeg và Remotion trên M1 Pro cho một tập 5 phút. Cần một benchmark ngắn khi làm adapter render.
- **Publish:**
  - `youtube.upload` có phải sensitive scope không, và app chưa verify ở production có giới hạn gì.
  - Hạn chế private với project chưa audit còn hiệu lực không.
  - Việt Nam có trong danh sách quốc gia của YouTube RSS ingestion không.
- **Testing:**
  - Azure F0: `WordBoundary` có chạy trên F0 không (chưa có trang nói rõ), dữ liệu có dùng để train không, và có giới hạn một resource F0 mỗi subscription không.
  - AWS Free plan: credit kết hợp với allowance 12 tháng của Polly như thế nào.
  - Groq: con số giới hạn riêng của free plan.
  - Cloudflare: một người được tạo bao nhiêu account free (để tách staging khỏi production).
  - Upload output phi thương mại lên kênh YouTube private có được tính là "non-commercial" không: không nhà cung cấp nào nói rõ.
  - Cartesia Free: speed, timestamps, en-GB.
- **Khác:**
  - ElevenLabs tính bao nhiêu credit mỗi ký tự theo từng model.
  - Gemini TTS: RPM/RPD và watermark SynthID.

## Nguồn (đọc ngày 2026-10-31)

**TTS**
- Azure: [pricing](https://azure.microsoft.com/en-us/pricing/details/speech/), [quotas](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits), [language support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts), [WordBoundary](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis), [SSML prosody](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice), [AI Code of Conduct](https://learn.microsoft.com/en-us/legal/ai-code-of-conduct)
- Azure, quyền thương mại (diễn đàn, ⚠️): [Q&A 2026](https://learn.microsoft.com/en-us/answers/questions/5805156/please-clarify-the-conflicting-information-regardi), [Q&A 2023](https://learn.microsoft.com/en-us/answers/questions/1192398/can-i-use-azure-text-to-speech-for-commercial-usag)
- Azure, giá (nguồn thứ ba, ⚠️): [developersdigest](https://www.developersdigest.tech/models/speech/azure), [beri.net](https://www.beri.net/article/elevenlabs-vs-cartesia-vs-azure-tts-latency-pricing-voice-cloning-2026)
- Amazon Polly: [pricing](https://aws.amazon.com/polly/pricing/), [AWS Free Tier](https://aws.amazon.com/free/), [speech marks](https://docs.aws.amazon.com/polly/latest/dg/speechmarks.html), [supported SSML tags](https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html), [available voices](https://docs.aws.amazon.com/polly/latest/dg/available-voices.html), [FAQ](https://aws.amazon.com/polly/faqs/)
- Google: [Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features), [Cloud TTS SSML](https://docs.cloud.google.com/text-to-speech/docs/ssml), [service terms](https://cloud.google.com/terms/service-terms), [Chirp 3: HD](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd), [voices](https://docs.cloud.google.com/text-to-speech/docs/voices), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Gemini speech generation](https://ai.google.dev/gemini-api/docs/speech-generation), [Gemini terms](https://ai.google.dev/gemini-api/terms)
- Google Cloud TTS, giá (⚠️): [trang pricing (bản cache)](https://cloud.google.com/text-to-speech/pricing?hl=fr), [costbench](https://costbench.com/software/ai-voice-tools/google-cloud-text-to-speech/)
- Hosted Kokoro: [DeepInfra Kokoro-82M](https://deepinfra.com/hexgrad/Kokoro-82M), [DeepInfra pricing](https://deepinfra.com/pricing), [DeepInfra terms](https://deepinfra.com/terms), [fal Kokoro](https://fal.ai/models/fal-ai/kokoro/american-english), [fal pricing](https://fal.ai/pricing), [fal terms](https://fal.ai/legal/terms-of-service), [Replicate Kokoro](https://replicate.com/jaaari/kokoro-82m), [Replicate pricing](https://replicate.com/pricing), [Together pricing](https://www.together.ai/pricing), [Kokoro model.py](https://raw.githubusercontent.com/hexgrad/kokoro/main/kokoro/model.py), [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
- Cloudflare TTS: [MeloTTS](https://developers.cloudflare.com/workers-ai/models/melotts/), [Aura-1](https://developers.cloudflare.com/workers-ai/models/aura-1/), [Aura-2-en](https://developers.cloudflare.com/workers-ai/models/aura-2-en/), [Aura-2-es](https://developers.cloudflare.com/workers-ai/models/aura-2-es/)
- ElevenLabs: [pricing](https://elevenlabs.io/pricing), [API pricing](https://elevenlabs.io/pricing/api), [terms](https://elevenlabs.io/terms-of-use), [with-timestamps](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)

**Alignment**
- Cloudflare: [whisper-large-v3-turbo](https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/), [whisper](https://developers.cloudflare.com/workers-ai/models/whisper/)
- Groq: [rate limits](https://console.groq.com/docs/rate-limits), [speech-to-text](https://console.groq.com/docs/speech-to-text)
- OpenAI: [speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text). Trang giá trả 403.
- Deepgram: [pricing](https://deepgram.com/pricing)

**Image**
- FLUX: [FLUX.1 schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell), [FLUX.1 dev license](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md), [FLUX.2 klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B), [BFL pricing](https://bfl.ai/pricing)
- Cloudflare: [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) (cập nhật 2026-10-20), [developer platform terms](https://www.cloudflare.com/service-specific-terms-developer-platform/) (cập nhật 2026-09-28), [REST API](https://developers.cloudflare.com/workers-ai/get-started/rest-api/), [flux-2-klein-4b](https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/), [flux-1-schnell](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
- Hosted fallback: [DeepInfra pricing](https://deepinfra.com/pricing), [fal FLUX schnell](https://fal.ai/models/fal-ai/flux/schnell), [Replicate flux-schnell](https://replicate.com/black-forest-labs/flux-schnell), [HF Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)
- Stability: [SDXL base](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), [Stability license](https://stability.ai/license)

**Testing (dev/staging)**
- AWS: [Free Tier docs](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html), [aws.amazon.com/free](https://aws.amazon.com/free/)
- Gemini: [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) (cập nhật 2026-10-28), [terms](https://ai.google.dev/gemini-api/terms)
- ElevenLabs: [terms](https://elevenlabs.io/terms-of-use) (cập nhật 2026-10-09). Help center trả 403.
- Google Cloud TTS: [voice types](https://docs.cloud.google.com/text-to-speech/docs/voice-types)
- Cartesia: [pricing](https://cartesia.ai/pricing); Together: [billing](https://docs.together.ai/docs/billing); Replicate: [billing](https://replicate.com/docs/topics/billing)
- Groq: [your data](https://console.groq.com/docs/your-data), [services agreement](https://console.groq.com/docs/legal/services-agreement) (cập nhật 2026-06-22)
- Cloudflare: [Workers AI limits](https://developers.cloudflare.com/workers-ai/platform/limits/) (cập nhật 2026-09-17)
- Hugging Face: [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu)

**Render**
- Remotion: [LICENSE.md](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md), [remotion.pro/license](https://www.remotion.pro/license), [Lambda cost example](https://www.remotion.dev/docs/lambda/cost-example)

**Publish**
- YouTube API: [quota cost](https://developers.google.com/youtube/v3/determine_quota_cost), [revision history](https://developers.google.com/youtube/v3/revision_history), [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert), [quota and compliance audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- YouTube policy: [GenAI disclosure](https://support.google.com/youtube/answer/14328491), [monetization policies](https://support.google.com/youtube/answer/1311392), [podcast RSS](https://support.google.com/youtube/answer/13525207)
- OAuth: [refresh token expiration](https://developers.google.com/identity/protocols/oauth2), [app verification](https://support.google.com/cloud/answer/13463073)
