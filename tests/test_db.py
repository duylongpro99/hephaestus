"""Migrations against a throwaway Postgres database."""

import re

import pytest

from factory.orchestrator.db import MIGRATIONS_DIR, migrate
from factory.orchestrator.states import State

pytestmark = pytest.mark.db


def test_migrate_is_idempotent(db):
    assert migrate(db) == []  # the fixture already applied everything
    versions = [r["version"] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions == ["0001"]


def test_schema_has_the_skeleton_tables(db):
    tables = {r["table_name"] for r in db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert {"channel", "episode", "artifact", "job", "gate_decision", "cost_ledger", "publish_receipt"} <= tables


def test_episode_status_check_lists_every_state():
    sql = (MIGRATIONS_DIR / "0001_init.sql").read_text(encoding="utf-8")
    block = re.search(r"status\s+text NOT NULL CHECK \(status IN \((.*?)\)\)", sql, re.S).group(1)
    assert set(re.findall(r"'(\w+)'", block)) == {s.value for s in State}


def test_one_receipt_per_episode_and_platform(db):
    db.execute("INSERT INTO channel (id, bible_version, pack, framework, audience) VALUES ('c', 1, 'xx', 'cefr', 'adult')")
    db.execute("INSERT INTO episode (id, channel, source, status, status_changed_at, config_hash, ordering, budget_usd, "
               "spec, resolved_config) VALUES ('e', 'c', 'adhoc', 'SPEC', now(), 'h', 'loose', 1, '{}', '{}')")
    insert = ("INSERT INTO publish_receipt (episode, platform, external_id, upload_ts, status) "
              "VALUES ('e', 'fake', %s, now(), 'private')")
    db.execute(insert, ("v1",))
    with pytest.raises(Exception, match="duplicate key"):
        db.execute(insert, ("v2",))
