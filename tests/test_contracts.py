import copy
import json

import pytest
from pydantic import ValidationError

from factory.config import CONFIG_DIR, load_yaml, pack_summary, resolve, resolve_layers
from factory.contracts import CONTRACTS, SCHEMA_VERSIONS, CostEntry, CostLedger, EpisodeSpec, GateDecision, Script
from factory.contracts.__main__ import SCHEMA_DIR, render
from tests.conftest import load_fixture


def test_fixtures_validate(spec, script):
    assert spec.level == "A2"
    assert script.episode_id == spec.episode_id
    assert [line.id for line in script.iter_lines()][:2] == ["s1l1", "s1l2"]


def test_every_contract_has_a_schema_version():
    assert set(SCHEMA_VERSIONS) == set(CONTRACTS)
    assert all(v.count(".") == 2 for v in SCHEMA_VERSIONS.values())


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_committed_schema_matches_model(name):
    """A schema change must be exported and must bump the contract's schema_version."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    committed = path.read_text()
    current = render(CONTRACTS[name])
    if committed != current:
        old_version = json.loads(committed)["properties"]["schema_version"]["default"]
        assert old_version != SCHEMA_VERSIONS[name], f"{name} schema changed: bump schema_version"
        pytest.fail(f"{name} schema changed: run `uv run python -m factory.contracts`")


def test_spec_rejects_bad_length():
    data = load_fixture("spec_example.json") | {"length_min": [8, 6]}
    with pytest.raises(ValidationError):
        EpisodeSpec.model_validate(data)


def test_spec_rejects_unknown_field():
    data = load_fixture("spec_example.json") | {"surprise": 1}
    with pytest.raises(ValidationError):
        EpisodeSpec.model_validate(data)


def test_script_rejects_duplicate_line_ids():
    data = load_fixture("script_example.json")
    data["segments"][1]["lines"][0]["id"] = "s1l1"
    with pytest.raises(ValidationError):
        Script.model_validate(data)


def test_gate_decision_and_ledger_round_trip():
    decision = GateDecision(episode_id="e1", gate=1, user="examiner", decision="edit-and-approve")
    assert GateDecision.model_validate_json(decision.model_dump_json()) == decision
    ledger = CostLedger(episode_id="e1", budget_usd=3.0, entries=[
        CostEntry(station="a2", model="m", usd=0.5), CostEntry(station="a3", model="m", usd=0.25),
    ])
    assert ledger.total_usd == 0.75
    assert ledger.station_usd("a3") == 0.25


def _layers():
    bible = load_yaml(CONFIG_DIR / "channels" / "en-podcast-spike.yaml")
    framework = load_yaml(CONFIG_DIR / "frameworks" / "cefr.yaml")
    audience = load_yaml(CONFIG_DIR / "audiences" / "adult.yaml")
    return pack_summary("en"), framework, audience, bible


def test_resolved_config_is_stable():
    first, second = resolve("en-podcast-spike", "A2"), resolve("en-podcast-spike", "A2")
    assert first.config_hash == second.config_hash
    assert first.config_hash.startswith("sha256:")
    assert first.band.rate.min == 100 and first.band.sentence_length == (8, 12)
    assert first.channel.support_languages == ["en", "vi"]


def test_hash_changes_when_a_band_changes():
    pack, framework, audience, bible = _layers()
    base = resolve_layers(pack, framework, audience, bible, "A2")
    changed = copy.deepcopy(framework)
    changed["bands"]["A2"]["coverage_min"] = 0.96
    assert resolve_layers(pack, changed, audience, bible, "A2").config_hash != base.config_hash


def test_later_layers_override_earlier_ones():
    pack, framework, audience, bible = _layers()
    audience = audience | {"band_overrides": {"coverage_min": 0.97}, "rate_multiplier": 0.9}
    bible = bible | {"band_overrides": {"coverage_min": 0.98}}
    config = resolve_layers(pack, framework, audience, bible, "A2")
    assert config.band.coverage_min == 0.98
    assert config.band.rate.min == pytest.approx(90)
    assert config.band.new_word_max == 0.05  # untouched keys survive the merge


def test_channel_format_must_be_allowed_by_audience():
    pack, framework, audience, bible = _layers()
    bible = bible | {"formats": ["song_tpr"]}
    with pytest.raises(ValidationError):
        resolve_layers(pack, framework, audience, bible, "A2")
