"""Rejects that send the script back: A3 revises it on the reviewers' notes, up to the rewrite limit."""

import json
import shutil
from datetime import datetime, timezone
from functools import cache

import pytest
from typer.testing import CliRunner

from factory.adapters import media
from factory.adapters.llm.fake import FakeLLMProvider
from factory.agents.review_panel.agent import PERSONAS
from factory.artifacts import ArtifactStore
from factory.cli import app
from factory.config import REPO_ROOT, resolve
from factory.contracts import EpisodeSpec, GateDecision, RevisionRequest, Script
from factory.orchestrator import repo, states
from factory.orchestrator.runner import Runner
from factory.orchestrator.stations import Stations, Vendors
from factory.orchestrator.states import MAX_REWRITES, State
from tests.conftest import FIXTURES
from tests.test_workers import CountingPublisher

pytestmark = [pytest.mark.e2e, pytest.mark.db]
SPECS = REPO_ROOT / "evals" / "xx-fixture" / "adult" / "specs"


def run_cli(db_url, tmp_path, monkeypatch, episode: str, exit_code: int = 0, auto_approve: bool = True) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    result = CliRunner().invoke(app, ["run", str(SPECS / f"{episode}.json"), "--fake-llm", "--artifacts", str(tmp_path),
                                      *(["--auto-approve"] if auto_approve else [])])
    assert result.exit_code == exit_code, result.output


def stored(db, store: ArtifactStore, episode: str, station: str, model):
    return [model.model_validate(store.read(row["uri"])["artifact"])
            for row in repo.artifacts(db, episode) if row["station"] == station]


def panel_jobs(db, episode: str) -> list[str]:
    return [j["status"] for j in repo.jobs(db, episode) if j["station"] == "review_panel"]


def lines(script: Script) -> dict[str, str]:
    return {line.id: line.text for line in script.iter_lines()}


def test_a_panel_reject_is_revised_and_the_episode_goes_on(db_url, db, tmp_path, monkeypatch):
    episode = "xx-A2-revise"
    run_cli(db_url, tmp_path, monkeypatch, episode)
    assert repo.get_episode(db, episode)["status"] == State.SCHEDULED
    assert panel_jobs(db, episode) == ["rejected", "succeeded"]
    store = ArtifactStore(tmp_path)
    first, revised = stored(db, store, episode, "a3_level_editor", Script)
    assert first != revised
    assert lines(revised)["s1l4"] == "Ta te sa kosa." and lines(first)["s1l4"] != "Ta te sa kosa."
    [request] = stored(db, store, episode, "revision_request", RevisionRequest)
    assert (request.round, request.rejected_by) == (1, "review_panel")
    [note] = request.notes
    assert note.reviewer == "examiner" and [i.line_id for i in note.issues] == ["s1l4"]


def test_rejects_past_the_rewrite_limit_escalate(db_url, db, tmp_path, monkeypatch):
    episode = "xx-A2-revise-cap"
    run_cli(db_url, tmp_path, monkeypatch, episode, exit_code=1)  # the run stops at ESCALATED
    assert repo.get_episode(db, episode)["status"] == State.ESCALATED
    assert panel_jobs(db, episode) == ["rejected"] * MAX_REWRITES + ["escalated"]
    assert repo.jobs(db, episode)[-1]["error"].startswith(f"rewrite limit reached ({MAX_REWRITES} of {MAX_REWRITES})")
    requests = stored(db, ArtifactStore(tmp_path), episode, "revision_request", RevisionRequest)
    assert [r.round for r in requests] == list(range(1, MAX_REWRITES + 1))
    scripts = stored(db, ArtifactStore(tmp_path), episode, "a3_level_editor", Script)
    assert len({s.model_dump_json() for s in scripts}) == MAX_REWRITES + 1  # every revision changed the script


def test_a_human_reject_at_gate_one_is_revised_on_the_next_run(db_url, db, tmp_path, monkeypatch):
    """Each `factory run` is a new process, so the fake LLM's call counts start over between the two runs."""
    episode = "xx-A2-revise-gate"
    run_cli(db_url, tmp_path, monkeypatch, episode, auto_approve=False)
    assert repo.get_episode(db, episode)["status"] == State.QA_OK
    result = CliRunner().invoke(app, ["decide", str(SPECS / f"{episode}.json"), "--gate", "1", "--decision", "reject",
                                      "--notes", "Kira should say when she wants the tea."])
    assert result.exit_code == 0, result.output
    run_cli(db_url, tmp_path, monkeypatch, episode, auto_approve=False)
    assert repo.get_episode(db, episode)["status"] == State.QA_OK  # revised, judged again, waiting for the human
    store = ArtifactStore(tmp_path)
    first, revised = stored(db, store, episode, "a3_level_editor", Script)
    assert lines(revised)["s1l3"] == "So bu! Mi pa te ju." and lines(first)["s1l3"] != lines(revised)["s1l3"]
    [request] = stored(db, store, episode, "revision_request", RevisionRequest)
    assert (request.round, request.rejected_by) == (1, "gate_1")
    assert [(n.reviewer, n.notes) for n in request.notes] == [("human", "Kira should say when she wants the tea.")]
    assert panel_jobs(db, episode) == ["succeeded", "succeeded"]


def in_process_runner(db, tmp_path, episode: str, fixtures) -> tuple[Runner, ArtifactStore]:
    """A runner whose fake LLMs keep one call count per role across every advance, unlike separate CLI runs."""
    spec = EpisodeSpec.model_validate_json((SPECS / f"{episode}.json").read_text(encoding="utf-8"))
    with db.transaction():
        repo.create_episode(db, spec, resolve(spec.channel, spec.level), datetime.now(timezone.utc))
    llm = cache(lambda role: FakeLLMProvider(fixtures))
    vendors = Vendors(llm=llm, speech=lambda pack: media.speech_for("fake", pack), images=media.image_for("fake"),
                      video=lambda pack: media.video_for("fake", pack), publisher=CountingPublisher(tmp_path))
    store = ArtifactStore(tmp_path / "store")
    return Runner(db, Stations(vendors).registry(), store, panel_users=tuple(PERSONAS)), store


def test_a_human_reject_at_gate_one_is_revised_then_waits_again(db, tmp_path):
    episode = "xx-A2-revise"
    runner, store = in_process_runner(db, tmp_path, episode, FIXTURES / "xx-fixture" / episode)

    def human_reject(notes: str) -> None:
        with db.transaction():
            repo.insert_gate_decision(db, GateDecision(episode_id=episode, gate=1, user="human", decision="reject",
                                                       notes=notes))

    assert runner.advance(episode) == State.QA_OK  # the panel rejected once, then approved the revision
    human_reject("Kira should say when she wants the tea.")
    assert runner.advance(episode) == State.QA_OK
    scripts = stored(db, store, episode, "a3_level_editor", Script)
    assert len(scripts) == 3 and lines(scripts[-1])["s1l3"] == "So bu! Mi pa te ju."
    request = stored(db, store, episode, "revision_request", RevisionRequest)[-1]
    assert (request.round, request.rejected_by) == (2, "gate_1")
    assert [(n.reviewer, n.notes) for n in request.notes] == [("human", "Kira should say when she wants the tea.")]
    assert panel_jobs(db, episode) == ["rejected", "succeeded", "succeeded"]  # the panel judged the new script

    human_reject("Still not right.")
    assert runner.advance(episode) == State.ESCALATED
    last = repo.jobs(db, episode)[-1]
    assert (last["station"], last["status"]) == ("gate_1", "escalated")
    assert last["error"] == f"rewrite limit reached ({MAX_REWRITES} of {MAX_REWRITES}): Still not right."


def test_a_revision_back_to_an_earlier_script_carries_that_scripts_notes(db, tmp_path, monkeypatch):
    """The panel's review of a script it already judged is reused, so the notes must follow the script itself."""
    monkeypatch.setattr(states, "MAX_REWRITES", 3)
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "xx-fixture" / "xx-A2-revise", fixtures)

    def write(name: str, data) -> None:
        (fixtures / name).write_text(json.dumps(data), encoding="utf-8")

    def edit(line_id: str, text: str, en: str) -> list[dict]:
        return [{"name": "edit_line", "arguments": {"line_id": line_id, "text": text, "translations": {"en": en}}}]

    def reject(line_id: str, description: str) -> dict:
        report = json.loads((fixtures / "review_examiner.1.json").read_text(encoding="utf-8"))
        report["issues"] = [report["issues"][0] | {"line_id": line_id, "description": description}]
        return report

    write("a3_level_editor.1.json", edit("s1l4", "Ta te sa kosa.", "The tea is cheap."))
    write("a3_level_editor.2.json", edit("s1l4", "Ta te sa so kosa.", "The tea is very cheap."))  # the draft again
    write("a3_level_editor.3.json", edit("s1l3", "So bu! Mi pa te ju.", "Very good! I want tea today."))
    write("review_examiner.1.json", reject("s1l4", "the draft's last line"))
    write("review_examiner.2.json", reject("s1l3", "the first revision's third line"))
    runner, store = in_process_runner(db, tmp_path, "xx-A2-revise", fixtures)

    assert runner.advance("xx-A2-revise") == State.QA_OK  # draft, revision, draft again (reused review), third
    requests = stored(db, store, "xx-A2-revise", "revision_request", RevisionRequest)
    assert [r.round for r in requests] == [1, 2, 3]
    described = [[i.description for n in r.notes for i in n.issues] for r in requests]
    assert described == [["the draft's last line"], ["the first revision's third line"], ["the draft's last line"]]
