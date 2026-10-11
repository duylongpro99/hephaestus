import pytest

from factory.adapters.llm.anthropic_client import price_usage
from factory.agents.a2_scriptwriter import agent as a2
from factory.agents.a3_level_editor.agent import EditSession
from factory.agents.drafts import draft_models, to_draft_dict, to_script
from factory.artifacts import ArtifactStore, artifact_hash, station_version
from factory.config import resolve
from factory.contracts import Script
from factory.tools.language_pack import load_pack


def test_artifact_hash_is_stable_and_input_sensitive(spec):
    version = "claude-opus-5-5+abc"
    first = artifact_hash([spec, "sha256:x"], version)
    assert first == artifact_hash([spec, "sha256:x"], version)
    assert first != artifact_hash([spec, "sha256:y"], version)
    assert first != artifact_hash([spec, "sha256:x"], "claude-opus-5-5+def")


def test_station_version_changes_with_prompt_and_model(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("v1")
    v1 = station_version("claude-opus-5-5", prompt)
    assert v1 == station_version("claude-opus-5-5", prompt)
    assert v1 != station_version("claude-sonnet-5-5", prompt)
    prompt.write_text("v2")
    assert v1 != station_version("claude-opus-5-5", prompt)


def test_store_round_trip(tmp_path, spec, script):
    store = ArtifactStore(tmp_path)
    where = {"channel": "c", "episode": spec.episode_id, "station": "a2", "version": "m+1", "inputs": [spec]}
    path = store.write(**where, artifact=script, extra={"cost": []})
    assert path.parent == tmp_path / "c" / "adhoc" / spec.episode_id
    assert path.name.startswith("a2@")
    envelope = store.read_envelope(**where)
    assert Script.model_validate(envelope["artifact"]) == script
    assert store.read_envelope(**(where | {"version": "m+2"})) is None


def test_a2_version_tracks_its_prompt():
    assert a2.version("claude-opus-5-5").startswith("claude-opus-5-5+")


def test_price_usage():
    class Usage:
        input_tokens, output_tokens = 1_000_000, 100_000
        cache_creation_input_tokens, cache_read_input_tokens = 0, 1_000_000

    assert price_usage("claude-opus-5-5", Usage) == pytest.approx(4.0 + 2.0 + 0.2)


def test_draft_round_trip(script):
    support = ["en", "vi"]
    draft_model = draft_models("en", tuple(support))
    schema = draft_model.model_json_schema()
    assert "translation_vi" in schema["$defs"]["DraftLine"]["properties"]
    assert "translation_en" not in schema["$defs"]["DraftLine"]["properties"]
    draft = draft_model.model_validate(to_draft_dict(script, "en", support))
    assert to_script(draft, script.episode_id, "en", support) == script


@pytest.fixture
def session(spec):
    example = Script.model_validate_json(a2.EXAMPLE_PATH.read_text(encoding="utf-8"))
    return EditSession(example, spec, resolve("en-podcast-spike", "A2"), load_pack("en"))


def lines_by_id(session):
    return {line.id: line for line in session.script.iter_lines()}


def test_editing_a_dialogue_line_updates_its_replay_copy(session):
    session.edit_line("s2l2", "Oh no! Where was your umbrella?", {"vi": "Ôi không! Ô của bạn đâu rồi?"})
    lines = lines_by_id(session)
    assert lines["s2l2"].text == lines["s4l2"].text == "Oh no! Where was your umbrella?"


def test_insert_in_dialogue_also_inserts_in_replay(session):
    session.insert_line("s2l1", "anna", "Really?", {"vi": "Thật à?"}, 1500)
    replay = next(s for s in session.script.segments if s.type == "replay")
    assert [line.text for line in replay.lines][:3] == [
        "Anna, I was riding my bike home yesterday when it started to rain.", "Really?",
        "Oh no! Did you have your umbrella?",
    ]
    assert len({line.id for line in session.script.iter_lines()}) == len(list(session.script.iter_lines()))


def test_edit_requires_every_translation(session):
    with pytest.raises(ValueError):
        session.edit_line("s3l1", "Let's look at borrow.", {})


def test_session_does_not_mutate_the_input(spec):
    example = Script.model_validate_json(a2.EXAMPLE_PATH.read_text(encoding="utf-8"))
    session = EditSession(example, spec, resolve("en-podcast-spike", "A2"), load_pack("en"))
    session.delete_line("s3l3")
    assert "s3l3" in {line.id for line in example.iter_lines()}
