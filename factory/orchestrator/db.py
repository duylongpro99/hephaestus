"""Postgres connection and versioned SQL migrations (architecture §10).

`DATABASE_URL` comes from the environment or the gitignored .env file.
"""

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class DatabaseError(RuntimeError):
    pass


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise DatabaseError("$DATABASE_URL is not set; copy it from .env.example and run `docker compose up -d db`")
    return url


def connect(url: str | None = None) -> psycopg.Connection:
    """An autocommit connection: reads commit at once, and `conn.transaction()` marks each atomic write."""
    try:
        return psycopg.connect(url or database_url(), row_factory=dict_row, autocommit=True)
    except psycopg.OperationalError as exc:
        raise DatabaseError(f"cannot connect to Postgres: {exc}".strip()) from exc


def migrations(directory: Path = MIGRATIONS_DIR) -> list[tuple[str, Path]]:
    """(version, path) pairs in order; the version is the file name's numeric prefix."""
    return sorted((path.name.split("_", 1)[0], path) for path in directory.glob("*.sql"))


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every migration not yet recorded, one transaction per file; return the versions applied."""
    with conn.transaction():
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                     "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    done = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, path in migrations(directory):
        if version in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        applied.append(version)
    return applied
