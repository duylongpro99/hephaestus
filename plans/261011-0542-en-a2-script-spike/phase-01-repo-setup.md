---
phase: 1
title: "Repo setup"
status: pending
priority: P1
effort: "1h"
dependencies: []
---

# Phase 1: Repo setup

## Goal
Turn the folder into a git repository with the §15 layout skeleton and a Python toolchain, and move the design docs into `docs/`.

## Files to Create / Modify
- Create: `.gitignore`. It covers `.env`, the uv virtualenv directory, `artifacts/`, `__pycache__/` and `packs/*/data/raw/`.
- Create: `pyproject.toml`. This is the uv project `yt-factory` on Python 3.12, with dependencies `pydantic`, `anthropic`, `spacy`, `wn` and `typer`, and dev dependency `pytest`.
- Create: `README.md`. It briefly says what the repo is, how to run the tests, and links to the docs.
- Move: `ARCHITECTURE.md` → `docs/architecture.md`
- Move: `RESEARCH.md` → `docs/research.md`
- Create empty packages: `factory/contracts/`, `factory/agents/`, `factory/tools/`, `factory/adapters/llm/`, `packs/en/`, `config/frameworks/`, `config/audiences/`, `config/channels/`, `evals/en/adult/specs/`

## Tasks & Steps
1. Run `git init` and create the `main` branch.
2. Move both docs and update their cross-references, so `RESEARCH.md §` becomes `research.md §`.
3. Run `uv init --package` and add the dependencies.
4. Install the spaCy model `en_core_web_sm` as a pinned wheel URL in `pyproject.toml`, so the install is reproducible.
5. Make the first commit: `chore: initialize repository layout`.

## Verification
- `git status` is clean after the commit.
- `uv run python -c "import spacy; print([t.lemma_ for t in spacy.load('en_core_web_sm')('She was running')])"` prints `['she', 'be', 'run']`.
- `grep -rn "RESEARCH.md" docs/` returns nothing.
