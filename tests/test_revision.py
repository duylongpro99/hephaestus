"""A3 revising a script on reviewer notes, with a fake LLM: no network, no database."""

import json

import pytest
from typer.testing import CliRunner

from factory.adapters.llm.fake import FakeLLMProvider
from factory.agents.a3_level_editor import agent as a3
from factory.artifacts import ArtifactStore, Producer, artifact_hash
from factory.cli import app
from factory.config import REPO_ROOT, resolve
from factory.contracts import EpisodeSpec, QAIssue, ReviewerNote, RevisionRequest, Script
from factory.orchestrator.stations import level_script, wordlist_hash
from factory.tools.language_pack import load_pack

EVALS = REPO_ROOT / "evals" / "en" / "adult"
NEW_TEXT = "Three, and I have already paid the rent."
EDIT = [{"name": "edit_line", "arguments": {"line_id": "s1l3", "text": NEW_TEXT,
                                            "translations": {"vi": "Ba phòng, và mình đã trả tiền thuê rồi."}}}]


class RecordingLLM(FakeLLMProvider):
    def __init__(self, fixtures_dir):
        super().__init__(fixtures_dir)
        self.users: list[str] = []

    def tool_loop(self, *, user, **kwargs):
        self.users.append(user)
        return super().tool_loop(user=user, **kwargs)


@pytest.fixture(scope="module")
def episode():
    spec = EpisodeSpec.model_validate_json((EVALS / "specs" / "en-A2-x01.json").read_text(encoding="utf-8"))
    script = Script.model_validate_json((EVALS / "scripts" / "en-A2-x01.json").read_text(encoding="utf-8"))
    return spec, resolve(spec.channel, spec.level), load_pack("en"), script


def revision(spec: EpisodeSpec) -> RevisionRequest:
    issue = QAIssue(line_id="s1l3", category="naturalness", severity="major",
                    description="the contraction is hard to hear at this level", suggested_fix=NEW_TEXT)
    return RevisionRequest(episode_id=spec.episode_id, round=1, rejected_by="review_panel", notes=[
        ReviewerNote(reviewer="examiner", gate=1, notes="slow the last line down", issues=[issue])])


def editor(tmp_path, calls: list[dict]) -> RecordingLLM:
    (tmp_path / f"{a3.STATION}.json").write_text(json.dumps(calls))
    return RecordingLLM(tmp_path)


def test_a_revision_runs_a_turn_on_a_passing_script_and_shows_the_notes(tmp_path, episode):
    spec, config, pack, script = episode
    llm = editor(tmp_path, EDIT)
    result = a3.level_loop(script, spec, config, pack, llm, revision=revision(spec))
    assert (result.status, result.turns, result.reason) == ("PASSED", 1, None)
    assert {line.id: line.text for line in result.script.iter_lines()}["s1l3"] == NEW_TEXT
    [user] = llm.users
    assert user.startswith("Reviewer feedback (rejected by review_panel, revision 1):")
    assert "examiner (gate 1): slow the last line down" in user
    assert f"[major] s1l3 (naturalness): the contraction is hard to hear at this level; suggested fix: {NEW_TEXT}" \
        in user
    assert "passes every code gate" in user


def test_a_revision_that_changes_nothing_escalates(tmp_path, episode):
    spec, config, pack, script = episode
    llm = editor(tmp_path, [{"name": "lexical_profile", "arguments": {}}])
    result = a3.level_loop(script, spec, config, pack, llm, revision=revision(spec))
    assert (result.status, result.turns, result.reason, result.error) == ("ESCALATED", 1, a3.NO_CHANGES, None)


def test_without_a_revision_a_passing_script_runs_no_turn(tmp_path, episode):
    spec, config, pack, script = episode
    llm = editor(tmp_path, EDIT)
    result = a3.level_loop(script, spec, config, pack, llm)
    assert (result.status, result.turns, result.script) == ("PASSED", 0, script)
    assert llm.users == []


def test_level_script_keys_on_the_revision_and_reuses_it(tmp_path, episode):
    spec, config, pack, script = episode
    (tmp_path / "llm").mkdir()
    llm, store = editor(tmp_path / "llm", EDIT), ArtifactStore(tmp_path / "store")
    out = Producer(store, spec.channel, spec.episode_id)
    plain = level_script(out, script, spec, config, pack, llm)
    inputs = [script, spec, config.config_hash, wordlist_hash(config, pack), 4]
    assert out.produced[0].envelope["hash"] == artifact_hash(inputs, a3.version(llm.identity))  # unchanged key
    assert plain.script == script

    revised = level_script(out, script, spec, config, pack, llm, revision=revision(spec))
    assert revised.script != script and revised.status == "PASSED" and revised.turns == 1
    assert out.produced[-2].envelope["hash"] != out.produced[0].envelope["hash"]

    again = Producer(store, spec.channel, spec.episode_id)
    assert level_script(again, script, spec, config, pack, llm, revision=revision(spec)).script == revised.script
    assert all(p.reused for p in again.produced)
    assert len(llm.users) == 1


def test_a_human_reject_needs_notes(tmp_path):
    spec_path = EVALS / "specs" / "en-A2-x01.json"
    result = CliRunner().invoke(app, ["decide", str(spec_path), "--decision", "reject"], env={"DATABASE_URL": ""})
    assert result.exit_code != 0
    assert "a gate 1 reject needs --notes" in result.output
