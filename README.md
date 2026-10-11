# yt-factory

A factory that turns a curriculum into level-graded language-learning episodes
for any target language, learner age and proficiency level. The current code is
the EN A2 script spike: the artifact contracts, the `en` Language Pack, the
lexical profiler, the Scriptwriter (A2) and Level Editor (A3) agents, and a
two-persona review panel.

## Setup

```bash
uv sync                      # installs Python 3.12 deps and the pinned spaCy model
uv run python -m packs.en.ingest   # downloads NGSL data and builds packs/en/data/lexicon.jsonl
export ANTHROPIC_API_KEY=...       # needed only for the agent commands
```

## Commands

```bash
uv run pytest                                            # all tests, no network
uv run factory profile <script.json> --spec <spec.json>  # code gates on a script
uv run factory script <spec.json>                        # A2 draft + A3 level loop
uv run factory review <script.json> --spec <spec.json>   # two-persona review panel
```

## Docs

- [Architecture](docs/architecture.md): the multi-agent factory design.
- [Research](docs/research.md): market, pedagogy and licensing research.
- [Decisions](docs/decisions/): architecture decision records.
