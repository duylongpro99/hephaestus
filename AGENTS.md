# AGENTS.md

Hướng dẫn cho mọi coding agent (Claude Code, Codex, Cursor, …) làm việc trong repo này.

## Ngôn ngữ

**Tiếng Việt là ngôn ngữ chính của project, áp dụng cho mọi session.**

- Trao đổi với người dùng, giải thích, câu hỏi, tóm tắt kết quả: viết bằng tiếng Việt.
- Plan mới (`plans/`), report (`plans/reports/`) và journal: viết bằng tiếng Việt.
- Giữ tiếng Anh cho: code, tên biến/hàm/file, comment trong code, commit message
  (conventional commits), JSON schema, prompt gửi cho LLM, và thuật ngữ kỹ thuật không có
  từ tương đương tự nhiên (ví dụ: station, gate, artifact, Language Pack).
- Tài liệu evergreen hiện có (`README.md`, `docs/`) đang viết bằng tiếng Anh: khi sửa thì
  giữ nguyên ngôn ngữ của file đó, trừ khi người dùng yêu cầu chuyển sang tiếng Việt.
- Khi giao việc cho subagent, ghi rõ yêu cầu này để subagent cũng trả lời bằng tiếng Việt.

## Project

`yt-factory` biến một curriculum thành các video học ngoại ngữ theo cấp độ, cho **bất kỳ**
ngôn ngữ đích, độ tuổi và trình độ nào. Ngôn ngữ, tuổi và level là dữ liệu cấu hình, không
phải code: station không bao giờ rẽ nhánh theo "Japanese" hay "kids" mà đọc từ bốn lớp cấu
hình (Language Pack, Level Framework, Audience Profile, Channel Bible). EN/JP/Kids chỉ là ví
dụ minh họa. Thiết kế đầy đủ ở [docs/architecture.md](docs/architecture.md).

Trạng thái hiện tại: spike script EN A2 (contracts, pack `en`, lexical profiler, agent
Scriptwriter A2 và Level Editor A3, review panel hai persona) cộng walking skeleton: orchestrator
dùng Postgres đưa một episode từ `SPEC` đến `SCHEDULED`, với TTS/image/publish giả và MP4
placeholder từ FFmpeg.

## Cấu trúc

- `factory/contracts/`: artifact contract (Pydantic) và JSON schema trong `schemas/`.
- `factory/agents/`: các bước LLM có giới hạn (`a2_scriptwriter`, `a3_level_editor`, `review_panel`).
- `factory/orchestrator/`: state machine, runner, stations, repo Postgres và `migrations/`.
- `factory/workers/`: các station không phải LLM (voice, visuals, composer, render, publisher, …).
- `factory/adapters/`: interface vendor (llm, tts, image, publish, ffmpeg) kèm bản fake.
- `factory/tools/`: profiler, rate estimator, language pack loader, enrichment.
- `packs/<lang>/`: Language Pack (`en`, `xx_fixture`); mỗi pack phải pass conformance test.
- `config/`: `llm.yaml` (provider theo role), `frameworks/`, `audiences/`, `channels/`.
- `evals/`: spec và kết quả đánh giá; `tests/fixtures/`: dữ liệu cho `--fake-llm`.
- `docs/decisions/`: ADR. `plans/`: plan, report, journal.

## Lệnh

```bash
uv sync                                   # Python 3.12 + spaCy model
uv run ruff check .                       # lint
uv run pytest                             # test, không cần mạng; bỏ qua db/e2e khi thiếu DATABASE_URL
uv run pytest -m "not db and not e2e"     # chỉ unit + conformance
docker compose up -d --wait db && uv run factory db migrate
uv run factory run <spec.json> [--auto-approve] [--fake-llm]
uv run factory status <episode_id>
scripts/ci.sh                             # CI local đầy đủ: lint, test, DB mới, episode xx-fixture end-to-end
```

Cần `ffmpeg`/`ffprobe` trên PATH cho test e2e. LLM endpoint cấu hình qua `.env`
(`LLM_GATEWAY_URL`, `LLM_GATEWAY_API_KEY`); xem `.env.example` và ADR 0002.

## Quy ước

- Orchestrator là state machine tất định; agent là bước LLM có input/output typed. Mọi artifact
  được validate bằng schema tại ranh giới station.
- Kiểm tra đo được thì làm bằng code trước, LLM judge sau, con người cuối cùng (hai gate).
- Không hard-code ngôn ngữ/tuổi/level trong `factory/`; đưa vào pack hoặc config.
- Side effect (upload, schedule, notify) phải idempotent theo episode và station.
- Ruff: line-length 120, target py312. Commit theo conventional commits, không nhắc tới AI.
- Không commit `.env`, secret, token hay dữ liệu cá nhân.
- Backup database trước mọi thay đổi schema hoặc dữ liệu.
- Quy tắc chi tiết cho Claude Code nằm trong `.claude/rules/`.
