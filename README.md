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
```

The agent commands call the LLM provider configured for each role in
[`config/llm.yaml`](config/llm.yaml). Set the key variable each provider names, for example
`DEEPSEEK_API_KEY` and `DASHSCOPE_API_KEY` for the default routing. See
[ADR 0002](docs/decisions/0002-per-role-llm-providers.md).

## Commands

```bash
uv run pytest                                            # all tests, no network
uv run factory profile <script.json> --spec <spec.json>  # code gates on a script
uv run factory script <spec.json>                        # A2 draft + A3 level loop
uv run factory review <spec.json>                        # two-persona review panel
uv run factory decide <spec.json> --decision ... --level-fit ...  # record a human spot-check
uv run factory summary evals/en/adult/specs              # aggregate runs and reviews
```

## Docs

- [Architecture](docs/architecture.md): the multi-agent factory design.
- [Research](docs/research.md): market, pedagogy and licensing research.
- [Decisions](docs/decisions/): architecture decision records, starting with
  [ADR 0001: first slice and spike scope](docs/decisions/0001-first-slice-and-spike-scope.md) and
  [ADR 0002: per-role LLM providers](docs/decisions/0002-per-role-llm-providers.md).
