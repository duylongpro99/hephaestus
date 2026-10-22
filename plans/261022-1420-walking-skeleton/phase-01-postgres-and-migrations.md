---
phase: 1
title: "Postgres and migrations"
status: pending
priority: P1
effort: "1d"
dependencies: []
---

# Phase 1: Postgres and migrations

## Goal
Run Postgres locally with Docker Compose and create the skeleton's tables from versioned SQL
migrations.

## Files to Create / Modify
- Create: `compose.yaml`: one `db` service (postgres 17), named volume, healthcheck, port 5432
  bound to localhost.
- Create: `factory/orchestrator/__init__.py`
- Create: `factory/orchestrator/db.py`: `connect()` from `DATABASE_URL`, `migrate()` applying
  `migrations/*.sql` in order inside a transaction, tracked in `schema_migrations`.
- Create: `factory/orchestrator/migrations/0001_init.sql`
- Modify: `pyproject.toml`: add `psycopg[binary]`.
- Modify: `.env.example`: `DATABASE_URL=postgresql://factory:factory@localhost:5432/factory`.
- Modify: `factory/cli.py`: `factory db migrate`.
- Create: `tests/test_db.py`: marked `db`, skipped when `DATABASE_URL` is unset.

## Tasks & Steps
1. Write `0001_init.sql` with the §10 tables the skeleton needs: `channel`, `episode`,
   `artifact`, `job`, `gate_decision`, `cost_ledger`, `publish_receipt`. Keep §10's column
   names. `episode.status` is text checked against the state list from phase 4.
   `publish_receipt` has a unique key on (episode, platform).
2. Write `migrate()`: create `schema_migrations(version, applied_at)`, apply each file whose
   version is missing, one transaction per file.
3. Register the `db` pytest marker; tests create a uniquely named database, migrate it, and drop
   it afterwards.

## Verification
- `docker compose up -d db && uv run factory db migrate` applies 0001; a second run applies none.
- `DATABASE_URL=... uv run pytest -m db` passes.

## Risk and rollback
Only new tables in a new database; rollback is `docker compose down -v`.
