import json
import os
import uuid
from pathlib import Path

import psycopg
import pytest

from factory.contracts import EpisodeSpec, Script
from factory.env import load_dotenv

load_dotenv()  # DATABASE_URL for the db-marked tests
FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def spec() -> EpisodeSpec:
    return EpisodeSpec.model_validate(load_fixture("spec_example.json"))


@pytest.fixture
def script() -> Script:
    return Script.model_validate(load_fixture("script_example.json"))


def pytest_collection_modifyitems(config, items):
    no_db = pytest.mark.skip(reason="DATABASE_URL is not set")
    no_live = pytest.mark.skip(reason="live provider tests run only with FACTORY_LIVE_TESTS=1")
    for item in items:
        if not os.environ.get("DATABASE_URL") and ("db" in item.keywords or "e2e" in item.keywords):
            item.add_marker(no_db)
        if os.environ.get("FACTORY_LIVE_TESTS") != "1" and "live" in item.keywords:
            item.add_marker(no_live)


@pytest.fixture
def db_url():
    """A fresh, migrated database for one test, dropped afterwards."""
    from psycopg.conninfo import make_conninfo

    from factory.orchestrator.db import connect, migrate

    base = os.environ["DATABASE_URL"]
    name = f"factory_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = make_conninfo(base, dbname=name)
    try:
        with connect(url) as conn:
            migrate(conn)
        yield url
    finally:
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def db(db_url):
    from factory.orchestrator.db import connect

    with connect(db_url) as conn:
        yield conn
