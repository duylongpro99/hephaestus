# yt-factory

A factory that turns a curriculum into level-graded language-learning episodes
for any target language, learner age and proficiency level. The current code is
the EN A2 script spike (the artifact contracts, the `en` Language Pack, the
lexical profiler, the Scriptwriter (A2) and Level Editor (A3) agents, and a
two-persona review panel) plus the walking skeleton: a Postgres-backed
orchestrator that takes an episode from `SPEC` to `SCHEDULED`, with fake TTS,
image and publish vendors and an FFmpeg placeholder MP4.

## Setup

```bash
uv sync                      # installs Python 3.12 deps and the pinned spaCy model
uv run python -m packs.en.ingest   # downloads NGSL data and builds packs/en/data/lexicon.jsonl
```

The agent commands call the LLM provider configured for each role in
[`config/llm.yaml`](config/llm.yaml). By default every role goes through one OpenAI-compatible
endpoint: copy `.env.example` to `.env` and set `LLM_GATEWAY_URL` and `LLM_GATEWAY_API_KEY`
(variables already set in the shell win). Then list the endpoint's models and set each role's
`model` to match:

```bash
uv run factory models gateway
```

See [ADR 0002](docs/decisions/0002-per-role-llm-providers.md).

The orchestrator keeps episode state in Postgres, run with Docker Compose
([`compose.yaml`](compose.yaml)). It also needs FFmpeg (`ffmpeg` and `ffprobe`) on the PATH.
Set `DATABASE_URL` in `.env` as in `.env.example`, then:

```bash
docker compose up -d --wait db
uv run factory db migrate                 # applies new migrations; a second run is a no-op
```

## Commands

```bash
uv run pytest                                            # all tests, no network
uv run factory profile <script.json> --spec <spec.json>  # code gates on a script
uv run factory script <spec.json>                        # A2 draft + A3 level loop
uv run factory review <spec.json>                        # two-persona review panel
uv run factory decide <spec.json> --decision ... --level-fit ...  # record a human spot-check
uv run factory summary evals/en/adult/specs              # aggregate runs and reviews
```

Orchestrator commands (need Postgres):

```bash
uv run factory run <spec.json>               # create the episode, run it until SCHEDULED or a human gate
uv run factory decide <spec.json> --gate 1 --decision approve   # open gate 1 (script) or 2 (final)
uv run factory run <spec.json>               # continue after the decision
uv run factory status <episode_id>           # state, jobs and spend against the budget
```

`factory run --auto-approve` approves both gates as user `auto`; `--fake-llm` serves every LLM
role from `tests/fixtures/<pack>/<episode>/`.

Speech, images, render and publishing go through the providers of a media profile in
[`config/media.yaml`](config/media.yaml): `fake` (the default, offline, what CI runs) or `live`
(Azure Speech, FLUX.2 [klein] on Cloudflare Workers AI, FFmpeg + Pillow, YouTube). Pick one with
`factory run --media-profile live` or `FACTORY_MEDIA_PROFILE`; the `live` secrets are listed in
`.env.example`. See [ADR 0004](docs/decisions/0004-purpose-oriented-media-adapters.md).

```bash
uv run factory media voices --profile live                  # pack voice key -> provider voice
uv run factory media check speech --profile live --text "Where is the station?" --rate 0.8
uv run factory media check image --profile live --prompt "a quiet train station at dawn"
uv run factory media check video --props <render_props.json> --artifacts <store root>
uv run factory media auth youtube --profile live            # once per environment; stores the token
uv run factory media check publishing --profile live --video <mp4> --package <publish_package.json>
FACTORY_LIVE_TESTS=1 uv run pytest -m live                   # conformance against the real providers
```

`scripts/ci.sh` checks the whole repository the way a hosted CI would: lint, unit and pack
conformance tests, a fresh migrated database, the database and end-to-end tests, and one
`xx-fixture` episode from `SPEC` to `SCHEDULED` with no LLM endpoint. It prints the failed step
and exits non-zero on any failure. Pytest skips the `db` and `e2e` tests when `DATABASE_URL` is
unset.

## Docs

- [Architecture](docs/architecture.md): the multi-agent factory design.
- [Research](docs/research.md): market, pedagogy and licensing research.
- [Decisions](docs/decisions/): architecture decision records, starting with
  [ADR 0001: first slice and spike scope](docs/decisions/0001-first-slice-and-spike-scope.md) and
  [ADR 0002: per-role LLM providers](docs/decisions/0002-per-role-llm-providers.md).
