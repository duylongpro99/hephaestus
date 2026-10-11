import json
from pathlib import Path

import pytest

from factory.contracts import EpisodeSpec, Script

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def spec() -> EpisodeSpec:
    return EpisodeSpec.model_validate(load_fixture("spec_example.json"))


@pytest.fixture
def script() -> Script:
    return Script.model_validate(load_fixture("script_example.json"))
