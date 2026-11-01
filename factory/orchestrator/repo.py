"""SQL for the orchestrator's tables (architecture §10). Callers own the transactions."""

import json
from datetime import datetime

import psycopg

from factory.config import ResolvedConfig
from factory.contracts import CostEntry, EpisodeSpec, GateDecision, PublishReceipt
from factory.orchestrator.states import (
    REWRITE_TARGETS,
    UPLOAD_RESOLUTIONS,
    IllegalTransition,
    State,
    check_transition,
)


class EpisodeExists(ValueError):
    pass


def upsert_channel(conn: psycopg.Connection, config: ResolvedConfig) -> None:
    bible = config.channel
    conn.execute(
        "INSERT INTO channel (id, bible_version, pack, framework, audience) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET bible_version = EXCLUDED.bible_version, pack = EXCLUDED.pack, "
        "framework = EXCLUDED.framework, audience = EXCLUDED.audience",
        (bible.channel, bible.version, config.pack.code, config.framework, config.audience.profile),
    )


def create_episode(conn: psycopg.Connection, spec: EpisodeSpec, config: ResolvedConfig, now: datetime,
                   media_profile: str = "fake") -> bool:
    """Insert the episode at SPEC with its pinned config and media profile; False if it already exists with both."""
    existing = get_episode(conn, spec.episode_id)
    if existing:
        if EpisodeSpec.model_validate(existing["spec"]) != spec:
            raise EpisodeExists(f"episode {spec.episode_id} already exists with a different spec")
        if existing["media_profile"] != media_profile:
            raise EpisodeExists(f"episode {spec.episode_id} runs on media profile {existing['media_profile']}, "
                                f"not {media_profile}")
        return False
    upsert_channel(conn, config)
    conn.execute(
        "INSERT INTO episode (id, channel, season, source, status, status_changed_at, config_hash, ordering, "
        "publish_slot, budget_usd, spec, resolved_config, media_profile) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (spec.episode_id, spec.channel, spec.season_id, spec.source, State.SPEC, now, config.config_hash,
         spec.ordering, spec.publish_slot, spec.budget_usd, spec.model_dump_json(), config.model_dump_json(),
         media_profile),
    )
    return True


def get_episode(conn: psycopg.Connection, episode: str) -> dict | None:
    return conn.execute("SELECT * FROM episode WHERE id = %s", (episode,)).fetchone()


def move(conn: psycopg.Connection, episode: str, src: State, dst: State, now: datetime) -> None:
    check_transition(src, dst)
    move_unchecked(conn, episode, src, dst, now)


def move_unchecked(conn: psycopg.Connection, episode: str, src: State, dst: State, now: datetime) -> None:
    cur = conn.execute(
        "UPDATE episode SET status = %s, status_changed_at = %s WHERE id = %s AND status = %s",
        (dst, now, episode, src),
    )
    if cur.rowcount != 1:
        raise RuntimeError(f"episode {episode} is no longer in {src}; another runner moved it")


def resolve_upload(conn: psycopg.Connection, episode: str, dst: State, now: datetime) -> None:
    """Move an episode whose upload escalated on, as an operator decided (`factory publish resolve`)."""
    if dst not in UPLOAD_RESOLUTIONS:
        raise IllegalTransition(f"an escalated upload resolves to {' or '.join(sorted(UPLOAD_RESOLUTIONS))}, not {dst}")
    move_unchecked(conn, episode, State.ESCALATED, dst, now)


def insert_job(
    conn: psycopg.Connection, *, episode: str, station: str, from_status: State, to_status: State | None,
    attempt: int, status: str, started_at: datetime, finished_at: datetime, error: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO job (episode, station, from_status, to_status, attempt, status, started_at, finished_at, error) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (episode, station, from_status, to_status, attempt, status, started_at, finished_at, error),
    )


def jobs(conn: psycopg.Connection, episode: str) -> list[dict]:
    return conn.execute("SELECT * FROM job WHERE episode = %s ORDER BY id", (episode,)).fetchall()


def count_jobs(
    conn: psycopg.Connection, episode: str, station: str, status: str | None = None, since: datetime | None = None,
) -> int:
    sql = "SELECT count(*) AS n FROM job WHERE episode = %s AND station = %s"
    params: tuple = (episode, station)
    if status:
        sql += " AND status = %s"
        params += (status,)
    if since:
        sql += " AND finished_at >= %s"
        params += (since,)
    return conn.execute(sql, params).fetchone()["n"]


def _rewrite_jobs(conn: psycopg.Connection, episode: str, select: str, tail: str = "") -> dict | None:
    return conn.execute(
        f"SELECT {select} FROM job WHERE episode = %s AND status = 'rejected' AND to_status = ANY(%s){tail}",
        (episode, sorted(REWRITE_TARGETS)),
    ).fetchone()


def count_rewrites(conn: psycopg.Connection, episode: str) -> int:
    """How many rejects sent the episode back for a rewrite, at any step."""
    return _rewrite_jobs(conn, episode, "count(*) AS n")["n"]


def last_rewrite_job(conn: psycopg.Connection, episode: str) -> dict | None:
    """The job of the latest reject that sent the episode back for a rewrite."""
    return _rewrite_jobs(conn, episode, "*", " ORDER BY id DESC LIMIT 1")


def insert_artifact(conn: psycopg.Connection, episode: str, envelope: dict, uri: str) -> bool:
    """Record a pointer to a stored artifact; False if the episode already points at it."""
    cur = conn.execute(
        "INSERT INTO artifact (episode, station, station_version, hash, uri, schema_version, artifact_type) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (episode, station, hash) DO NOTHING",
        (episode, envelope["station"], envelope["station_version"], envelope["hash"], uri,
         envelope["artifact"].get("schema_version", ""), envelope["artifact_type"]),
    )
    return cur.rowcount == 1


def latest_artifact(conn: psycopg.Connection, episode: str, station: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM artifact WHERE episode = %s AND station = %s ORDER BY id DESC LIMIT 1", (episode, station),
    ).fetchone()


def artifacts(conn: psycopg.Connection, episode: str) -> list[dict]:
    return conn.execute("SELECT * FROM artifact WHERE episode = %s ORDER BY id", (episode,)).fetchall()


def add_costs(conn: psycopg.Connection, episode: str, entries: list[CostEntry]) -> None:
    """Record what the entries billed; an entry whose dedupe key the episode already has is skipped."""
    for e in entries:
        units = {"input_tokens": e.input_tokens, "output_tokens": e.output_tokens,
                 "cache_creation_input_tokens": e.cache_creation_input_tokens,
                 "cache_read_input_tokens": e.cache_read_input_tokens}
        conn.execute(
            "INSERT INTO cost_ledger (episode, station, vendor, model, units, usd, priced, ts, dedupe_key) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (episode, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
            (episode, e.station, e.vendor, e.model, json.dumps(units), e.usd, e.priced, e.timestamp, e.dedupe_key),
        )


def spent_usd(conn: psycopg.Connection, episode: str) -> float:
    row = conn.execute("SELECT coalesce(sum(usd), 0) AS usd FROM cost_ledger WHERE episode = %s", (episode,)).fetchone()
    return float(row["usd"])


def insert_gate_decision(conn: psycopg.Connection, decision: GateDecision) -> None:
    conn.execute(
        'INSERT INTO gate_decision (episode, gate, "user", decision, diff, notes, ts) '
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (decision.episode_id, decision.gate, decision.user, decision.decision, decision.diff, decision.notes,
         decision.timestamp),
    )


def gate_decision_since(
    conn: psycopg.Connection, episode: str, gate: int, since: datetime, exclude_users: tuple[str, ...] = (),
    decisions: tuple[str, ...] | None = None,
) -> dict | None:
    """The latest decision at `gate` made after the episode reached it, ignoring `exclude_users`.

    `decisions` narrows the match to those decision values, e.g. only rejects.
    """
    wanted = None if decisions is None else list(decisions)
    return conn.execute(
        'SELECT * FROM gate_decision WHERE episode = %s AND gate = %s AND ts >= %s AND NOT ("user" = ANY(%s)) '
        "AND (%s::text[] IS NULL OR decision = ANY(%s::text[])) ORDER BY ts DESC, id DESC LIMIT 1",
        (episode, gate, since, list(exclude_users), wanted, wanted),
    ).fetchone()


def _receipt(row: dict) -> PublishReceipt:
    return PublishReceipt(episode_id=row["episode"], platform=row["platform"], external_id=row["external_id"],
                          upload_ts=row["upload_ts"], publish_at=row["publish_at"], status=row["status"],
                          quota_units=row["quota_units"])


def get_receipt(conn: psycopg.Connection, episode: str, platform: str) -> PublishReceipt | None:
    row = conn.execute(
        "SELECT * FROM publish_receipt WHERE episode = %s AND platform = %s", (episode, platform),
    ).fetchone()
    return _receipt(row) if row else None


def receipts(conn: psycopg.Connection, episode: str) -> list[PublishReceipt]:
    rows = conn.execute("SELECT * FROM publish_receipt WHERE episode = %s ORDER BY id", (episode,)).fetchall()
    return [_receipt(row) for row in rows]


def insert_receipt(conn: psycopg.Connection, receipt: PublishReceipt) -> None:
    conn.execute(
        "INSERT INTO publish_receipt (episode, platform, external_id, upload_ts, publish_at, status, quota_units) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (receipt.episode_id, receipt.platform, receipt.external_id, receipt.upload_ts, receipt.publish_at,
         receipt.status, receipt.quota_units),
    )


def get_attempt(conn: psycopg.Connection, episode: str, platform: str) -> datetime | None:
    """When an upload of this episode to `platform` started without a receipt to show for it."""
    row = conn.execute(
        "SELECT started_at FROM publish_attempt WHERE episode = %s AND platform = %s", (episode, platform),
    ).fetchone()
    return row["started_at"] if row else None


def insert_attempt(conn: psycopg.Connection, episode: str, platform: str, started_at: datetime) -> None:
    conn.execute("INSERT INTO publish_attempt (episode, platform, started_at) VALUES (%s, %s, %s)",
                 (episode, platform, started_at))


def delete_attempt(conn: psycopg.Connection, episode: str, platform: str) -> None:
    conn.execute("DELETE FROM publish_attempt WHERE episode = %s AND platform = %s", (episode, platform))


def schedule_receipt(conn: psycopg.Connection, receipt: PublishReceipt) -> None:
    conn.execute(
        "UPDATE publish_receipt SET publish_at = %s, status = 'scheduled', quota_units = %s "
        "WHERE episode = %s AND platform = %s",
        (receipt.publish_at, receipt.quota_units, receipt.episode_id, receipt.platform),
    )
