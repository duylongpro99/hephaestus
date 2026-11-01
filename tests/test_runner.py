"""The runner against Postgres, with toy stations: jobs, artifacts, retries, budget, gates and resume."""

from collections import Counter
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from factory.adapters.costs import MediaError
from factory.adapters.speech import base as speech_base
from factory.adapters.publishing.export import ExportPublisher
from factory.artifacts import ArtifactStore, Built, station_version
from factory.cli import app
from factory.config import resolve
from factory.contracts import CostEntry, EpisodeSpec, GateDecision, PublishPackage, QAReport, RenderedVideo, Script
from factory.orchestrator import repo
from factory.orchestrator.runner import Runner, StationResult
from factory.orchestrator.stations import Stations, Vendors
from factory.orchestrator.states import MAX_REWRITES, PIPELINE, State
from factory.agents.drafts import draft_models, to_script
from factory.tools.language_pack import load_pack
from factory.workers import publisher, voice
from tests import test_workers
from tests.test_workers import EPISODE, SPEC_PATH, VOICES, CountingPublisher, PricedSpeech, SchedulingPublisher

pytestmark = pytest.mark.db
STATIONS = [step.station for step in PIPELINE.values() if step.gate is None]


class FakeClock:
    def __init__(self):
        self.t = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class Crash(BaseException):
    """A process dying mid-station: nothing after it runs, not even the runner's error handling."""


class Toys:
    """One toy station per pipeline step; each writes a QAReport artifact and can cost, fail or reject."""

    def __init__(self):
        self.builds: Counter[str] = Counter()
        self.usd: dict[str, float] = {}
        self.raise_in: dict[str, type[BaseException]] = {}
        self.outcome: dict[str, str] = {}

    def station(self, name: str):
        def run(ctx):
            def build(media):
                self.builds[name] += 1
                costs = [CostEntry(station=name, vendor="toy", model="toy", usd=self.usd[name])] if name in self.usd else []
                return Built(QAReport(episode_id=ctx.episode, reviewer=name), costs)

            ctx.produce(name, "toy+1", [ctx.spec, name], QAReport, build)
            if name in self.raise_in:
                raise self.raise_in[name](f"{name} broke")
            return StationResult(self.outcome.get(name, "ok"), error="toy says no" if name in self.outcome else None)
        return run

    def registry(self):
        return {name: self.station(name) for name in STATIONS}


@pytest.fixture
def spec():
    return EpisodeSpec.model_validate_json(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def episode(db, spec):
    with db.transaction():
        repo.create_episode(db, spec, resolve(spec.channel, spec.level), datetime(2026, 10, 22, tzinfo=timezone.utc))
    return spec.episode_id


def runner(db, toys, tmp_path, clock=None, auto_approve=True):
    return Runner(db, toys.registry(), ArtifactStore(tmp_path), clock=clock or FakeClock(), auto_approve=auto_approve)


def test_auto_approved_run_reaches_scheduled_with_a_job_per_change(db, tmp_path, episode):
    toys = Toys()
    assert runner(db, toys, tmp_path).advance(episode) == State.SCHEDULED
    jobs = repo.jobs(db, episode)
    assert [(j["from_status"], j["to_status"]) for j in jobs] == [(s.value, step.next.value) for s, step in PIPELINE.items()]
    assert all(j["status"] == "succeeded" for j in jobs)
    decisions = db.execute('SELECT gate, "user" FROM gate_decision ORDER BY gate').fetchall()
    assert decisions == [{"gate": 1, "user": "auto"}, {"gate": 2, "user": "auto"}]


def test_artifact_rows_point_at_matching_envelopes(db, tmp_path, episode):
    runner(db, Toys(), tmp_path).advance(episode)
    store, rows = ArtifactStore(tmp_path), repo.artifacts(db, episode)
    assert len(rows) == len(STATIONS)
    for row in rows:
        envelope = store.read(row["uri"])
        assert (envelope["hash"], envelope["station"], envelope["station_version"]) == (
            row["hash"], row["station"], row["station_version"])


def test_without_auto_approve_the_run_waits_at_each_gate(db, tmp_path, episode):
    toys, clock = Toys(), FakeClock()
    assert runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode) == State.QA_OK
    assert runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode) == State.QA_OK  # still waiting
    with db.transaction():
        repo.insert_gate_decision(db, GateDecision(episode_id=episode, gate=1, user="human", decision="approve",
                                                   timestamp=clock.now()))
    assert runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode) == State.COMPLIANT


def test_panel_verdicts_do_not_open_the_human_gate(db, tmp_path, episode):
    clock = FakeClock()
    r = Runner(db, Toys().registry(), ArtifactStore(tmp_path), clock=clock, panel_users=("examiner",))
    assert r.advance(episode) == State.QA_OK
    with db.transaction():
        repo.insert_gate_decision(db, GateDecision(episode_id=episode, gate=1, user="examiner", decision="approve",
                                                   timestamp=clock.now()))
    assert r.advance(episode) == State.QA_OK


def test_human_reject_at_gate_one_sends_the_script_back(db, tmp_path, episode):
    toys, clock = Toys(), FakeClock()
    runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode)
    with db.transaction():
        repo.insert_gate_decision(db, GateDecision(episode_id=episode, gate=1, user="human", decision="reject",
                                                   notes="too fast", timestamp=clock.now()))
    assert runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode) == State.QA_OK
    gate_jobs = [j for j in repo.jobs(db, episode) if j["station"] == "gate_1"]
    assert [(j["status"], j["to_status"], j["error"]) for j in gate_jobs] == [("rejected", "DRAFTED", "too fast")]
    assert toys.builds["a3_level_editor"] == 1  # the rerun reused the stored output


def test_retries_back_off_then_escalate_with_the_error(db, tmp_path, episode):
    toys, clock = Toys(), FakeClock()
    toys.raise_in["voice"] = RuntimeError
    assert runner(db, toys, tmp_path, clock).advance(episode) == State.ESCALATED
    voice_jobs = [j for j in repo.jobs(db, episode) if j["station"] == "voice"]
    assert [(j["attempt"], j["status"]) for j in voice_jobs] == [(1, "retrying"), (2, "retrying"), (3, "escalated")]
    assert voice_jobs[-1]["error"] == "RuntimeError: voice broke"
    assert clock.sleeps == [1.0, 2.0]


def test_panel_rejects_until_the_rewrite_limit_then_escalates(db, tmp_path, episode):
    toys = Toys()
    toys.outcome["review_panel"] = "reject"
    assert runner(db, toys, tmp_path).advance(episode) == State.ESCALATED
    panel_jobs = [(j["status"], j["to_status"]) for j in repo.jobs(db, episode) if j["station"] == "review_panel"]
    assert panel_jobs == [("rejected", "DRAFTED")] * MAX_REWRITES + [("escalated", "ESCALATED")]
    assert repo.jobs(db, episode)[-1]["error"] == f"rewrite limit reached ({MAX_REWRITES} of {MAX_REWRITES}): toy says no"


def human_decision(db, episode, clock, decision, gate=1, notes="too fast"):
    with db.transaction():
        repo.insert_gate_decision(db, GateDecision(episode_id=episode, gate=gate, user="human", decision=decision,
                                                   notes=notes, timestamp=clock.now()))


def test_panel_and_gate_one_rejects_share_one_rewrite_limit(db, tmp_path, episode):
    toys, clock = Toys(), FakeClock()
    toys.outcome["review_panel"] = "reject"
    r = Runner(db, toys.registry(), ArtifactStore(tmp_path), clock=clock)
    with db.transaction():  # the panel rejects once, then approves
        repo.insert_job(db, episode=episode, station="review_panel", from_status=State.ENRICHED,
                        to_status=State.DRAFTED, attempt=1, status="rejected", started_at=clock.now(),
                        finished_at=clock.now())
    del toys.outcome["review_panel"]
    assert r.advance(episode) == State.QA_OK
    for _ in range(MAX_REWRITES - 1):
        human_decision(db, episode, clock, "reject")
        assert r.advance(episode) == State.QA_OK
    assert repo.count_rewrites(db, episode) == MAX_REWRITES
    human_decision(db, episode, clock, "reject")
    assert r.advance(episode) == State.ESCALATED
    last = repo.jobs(db, episode)[-1]
    assert (last["station"], last["status"]) == ("gate_1", "escalated")
    assert last["error"] == f"rewrite limit reached ({MAX_REWRITES} of {MAX_REWRITES}): too fast"


def test_a_final_gate_reject_does_not_count_as_a_rewrite(db, tmp_path, episode):
    toys, clock = Toys(), FakeClock()
    r = Runner(db, toys.registry(), ArtifactStore(tmp_path), clock=clock)
    assert r.advance(episode) == State.QA_OK
    human_decision(db, episode, clock, "approve")
    assert r.advance(episode) == State.COMPLIANT
    human_decision(db, episode, clock, "reject", gate=2)
    assert r.advance(episode) == State.ESCALATED
    assert repo.count_rewrites(db, episode) == 0


def test_budget_stop(db, tmp_path, episode):
    toys = Toys()
    toys.usd |= {"a2_scriptwriter": 0.6, "a3_level_editor": 0.6}  # the spec's budget is $1
    assert runner(db, toys, tmp_path).advance(episode) == State.BUDGET_EXCEEDED
    last = repo.jobs(db, episode)[-1]
    assert (last["station"], last["from_status"], last["to_status"]) == ("budget", "LEVEL_OK", "BUDGET_EXCEEDED")
    assert repo.spent_usd(db, episode) == pytest.approx(1.2)


def test_resume_after_a_crash_reuses_the_stored_output(db, tmp_path, episode):
    toys = Toys()
    toys.usd["visuals"] = 0.25
    toys.raise_in["visuals"] = Crash
    with pytest.raises(Crash):
        runner(db, toys, tmp_path).advance(episode)
    assert repo.get_episode(db, episode)["status"] == State.VOICED  # the crashed step left no trace in the DB
    del toys.raise_in["visuals"]
    assert runner(db, toys, tmp_path).advance(episode) == State.SCHEDULED
    assert toys.builds["visuals"] == 1  # built once, before the crash
    assert repo.spent_usd(db, episode) == pytest.approx(0.25)  # what the crashed attempt paid, counted once


def test_a_rewind_does_not_charge_reused_outputs_again(db, tmp_path, episode):
    toys, clock = Toys(), FakeClock()
    toys.usd["a3_level_editor"] = 0.25
    runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode)
    with db.transaction():
        repo.insert_gate_decision(db, GateDecision(episode_id=episode, gate=1, user="human", decision="reject",
                                                   timestamp=clock.now()))
    runner(db, toys, tmp_path, clock, auto_approve=False).advance(episode)
    assert repo.spent_usd(db, episode) == pytest.approx(0.25)


def test_a_second_runner_on_the_same_episode_is_refused(db, db_url, tmp_path, episode):
    from factory.orchestrator.db import connect
    from factory.orchestrator.runner import EpisodeBusy

    with connect(db_url) as other:
        other.execute("SELECT pg_advisory_lock(hashtext(%s))", (episode,))
        with pytest.raises(EpisodeBusy):
            runner(db, Toys(), tmp_path).advance(episode)
    assert runner(db, Toys(), tmp_path).advance(episode) == State.SCHEDULED  # the lock went with the connection


def test_the_retry_cap_holds_across_restarts(db, tmp_path, episode):
    toys = Toys()
    toys.raise_in["voice"] = RuntimeError
    toys.raise_in["visuals"] = Crash  # never reached; voice escalates first
    clock = FakeClock()
    r = runner(db, toys, tmp_path, clock)
    with db.transaction():  # one retry already recorded before a restart
        repo.insert_job(db, episode=episode, station="voice", from_status=State.SCRIPT_APPROVED, to_status=None,
                        attempt=1, status="retrying", started_at=clock.now(), finished_at=clock.now())
    db.execute("UPDATE episode SET status = 'SCRIPT_APPROVED', status_changed_at = %s WHERE id = %s",
               (clock.t - timedelta(seconds=10), episode))
    assert r.advance(episode) == State.ESCALATED
    voice_jobs = [(j["attempt"], j["status"]) for j in repo.jobs(db, episode) if j["station"] == "voice"]
    assert voice_jobs == [(1, "retrying"), (2, "retrying"), (3, "escalated")]


def test_an_episode_already_over_budget_runs_no_station(db, tmp_path, episode):
    with db.transaction():
        repo.add_costs(db, episode, [CostEntry(station="a2_scriptwriter", vendor="toy", model="toy", usd=2.0)])
    toys = Toys()
    assert runner(db, toys, tmp_path).advance(episode) == State.BUDGET_EXCEEDED
    assert not toys.builds


def test_an_episode_keeps_the_media_profile_it_was_created_with(db, spec, episode):
    config, now = resolve(spec.channel, spec.level), datetime(2026, 10, 23, tzinfo=timezone.utc)
    assert repo.get_episode(db, episode)["media_profile"] == "fake"
    assert repo.create_episode(db, spec, config, now, "fake") is False
    with pytest.raises(repo.EpisodeExists, match="media profile fake, not live"):
        repo.create_episode(db, spec, config, now, "live")


def test_a_media_failure_still_records_what_its_earlier_requests_billed(db, tmp_path, episode):
    class ProviderDown(MediaError):
        def __init__(self, message):
            super().__init__(message)
            self.costs = [CostEntry(station="c4_tts", vendor="speechco", model="v1", usd=0.5)]

    toys = Toys()
    toys.raise_in["voice"] = ProviderDown
    assert runner(db, toys, tmp_path).advance(episode) == State.ESCALATED
    attempts = sum(1 for j in repo.jobs(db, episode) if j["station"] == "voice")
    assert attempts > 1 and repo.spent_usd(db, episode) == pytest.approx(0.5 * attempts)


@pytest.fixture
def pack():
    return load_pack("xx-fixture")


@pytest.fixture
def script(spec):
    draft = draft_models("xx-fixture", ("en",)).model_validate_json((EPISODE / "a2_scriptwriter.json").read_text())
    return to_script(draft, spec.episode_id, "xx-fixture", ["en"])


def voicing_toys(script, speech) -> dict:
    """Toy stations, except that A3 stores the fixture script and voice is the real station on `speech`."""
    toys = Toys()
    registry = toys.registry()

    def level_editor(ctx):
        ctx.produce("a3_level_editor", "toy+1", [ctx.spec], Script, lambda media: Built(script))
        return StationResult()

    vendors = Vendors(llm=None, speech=lambda pack: speech, images=None, video=None, publisher=None)
    return {**registry, "a3_level_editor": level_editor, "voice": Stations(vendors).voice_lines}


def voice_runner(db, registry, tmp_path):
    return Runner(db, registry, ArtifactStore(tmp_path), clock=FakeClock(), auto_approve=True)


def test_voice_retry_after_a_failure_charges_each_line_once(db, tmp_path, episode, script, pack):
    speech = PricedSpeech(pack, VOICES, fail_on={3})
    assert voice_runner(db, voicing_toys(script, speech), tmp_path).advance(episode) == State.SCHEDULED
    voice_jobs = [j["status"] for j in repo.jobs(db, episode) if j["station"] == "voice"]
    lines = len(list(script.iter_lines()))
    assert voice_jobs == ["retrying", "succeeded"] and len(speech.calls) == lines + 1
    assert repo.spent_usd(db, episode) == pytest.approx(0.25 * lines)


def test_a_killed_voice_attempt_is_charged_when_the_retry_succeeds(db, tmp_path, episode, script, pack):
    killed = PricedSpeech(pack, VOICES, fail_on={3}, error=Crash)  # same class, so the same station_version
    with pytest.raises(Crash):
        voice_runner(db, voicing_toys(script, killed), tmp_path).advance(episode)
    assert repo.spent_usd(db, episode) == 0  # the process died before the runner could record anything
    speech = PricedSpeech(pack, VOICES)
    assert voice_runner(db, voicing_toys(script, speech), tmp_path).advance(episode) == State.SCHEDULED
    lines = len(list(script.iter_lines()))
    assert len(speech.calls) == lines - 2
    assert repo.spent_usd(db, episode) == pytest.approx(0.25 * lines)


def test_a_rate_the_synthesizer_cannot_speak_escalates_without_retrying(db, tmp_path, episode, script, pack):
    class Narrow(PricedSpeech):
        rate_range = (1.5, 2.0)

    speech = Narrow(pack, VOICES)
    assert voice_runner(db, voicing_toys(script, speech), tmp_path).advance(episode) == State.ESCALATED
    [job] = [j for j in repo.jobs(db, episode) if j["station"] == "voice"]
    assert job["status"] == "escalated" and "outside the synthesizer's 1.50-2.00" in job["error"]
    assert speech.calls == [] and repo.spent_usd(db, episode) == 0


def test_the_voice_station_version_follows_the_worker_and_adapter_source(db, tmp_path, episode, script, pack):
    speech = PricedSpeech(pack, VOICES)
    voice_runner(db, voicing_toys(script, speech), tmp_path).advance(episode)
    stored = repo.latest_artifact(db, episode, "c5_audio")["station_version"]
    sources = [Path(m.__file__) for m in (voice, speech_base, test_workers)]
    assert stored == station_version(speech.identity, *sources)
    edited = tmp_path / "edited" / "voice.py"
    edited.parent.mkdir()
    edited.write_text(sources[0].read_text() + "\n# changed\n")
    assert station_version(speech.identity, edited, *sources[1:]) != stored


def publishing_toys(publisher) -> dict:
    """Toy stations, except that packaging and render store a real package and video, and upload and schedule
    are the real stations on `publisher`."""
    registry = Toys().registry()
    package = PublishPackage(episode_id="", video_uri="render/master.mp4", title={"en": "t"}, description={"en": "d"},
                             tags={"en": []}, chapters=[], made_for_kids=False, contains_synthetic_media=True)

    def packager(ctx):
        ctx.produce("a9_packager", "toy+1", [ctx.spec], PublishPackage,
                    lambda media: Built(package.model_copy(update={"episode_id": ctx.episode})))
        return StationResult()

    def render(ctx):
        clip = ctx.store.root / "toy-master.mp4"
        clip.write_bytes(b"not really a video")
        ctx.produce("c8_render", "toy+1", [ctx.spec], RenderedVideo, lambda media: Built(RenderedVideo(
            episode_id=ctx.episode, uri=clip.name, sha256="0" * 64, size_bytes=18, width=16, height=9, fps=25)))
        return StationResult()

    stations = Stations(Vendors(llm=None, speech=None, images=None, video=None, publisher=publisher))
    return {**registry, "a9_packager": packager, "render": render,
            "c10_upload": stations.upload, "c10_schedule": stations.schedule}


def test_a_crash_after_insert_does_not_upload_twice(db, tmp_path, episode):
    pub = CountingPublisher(tmp_path / "_export", fail=Crash("killed after the insert"), after_copy=True)
    with pytest.raises(Crash):
        voice_runner(db, publishing_toys(pub), tmp_path).advance(episode)
    assert repo.get_attempt(db, episode, "export") is not None and repo.receipts(db, episode) == []
    pub.hidden_finds = pub.finds + 2  # the new video shows up on the third lookup
    clock = FakeClock()
    r = Runner(db, publishing_toys(pub), ArtifactStore(tmp_path), clock=clock, auto_approve=True)
    assert r.advance(episode) == State.SCHEDULED
    [receipt] = repo.receipts(db, episode)
    assert pub.uploads == 1 and receipt.external_id == ExportPublisher(tmp_path / "_export").find(episode)[0]
    assert clock.sleeps == [publisher.MARKER_POLL_INTERVAL_S] * 2
    assert repo.get_attempt(db, episode, "export") is None


def interrupted_upload(db, tmp_path, episode) -> CountingPublisher:
    """An episode escalated at c10_upload: its upload started, and the video cannot be found."""
    pub = CountingPublisher(tmp_path / "_export", fail=Crash("killed mid-upload"))
    with pytest.raises(Crash):
        voice_runner(db, publishing_toys(pub), tmp_path).advance(episode)
    pub.hidden_finds = 10**6
    assert voice_runner(db, publishing_toys(pub), tmp_path).advance(episode) == State.ESCALATED
    return pub


def test_an_upload_marker_without_a_video_escalates_for_an_operator(db, tmp_path, episode):
    pub = interrupted_upload(db, tmp_path, episode)
    last = repo.jobs(db, episode)[-1]
    assert (last["station"], last["status"]) == ("c10_upload", "escalated")
    assert "factory publish resolve" in last["error"] and pub.uploads == 1


def publish_resolve(db_url, monkeypatch, tmp_path, *args):
    monkeypatch.setenv("DATABASE_URL", db_url)
    return CliRunner().invoke(app, ["publish", "resolve", *args, "--artifacts", str(tmp_path)])


def test_resolve_with_an_external_id_moves_the_episode_to_uploaded(db, db_url, monkeypatch, tmp_path, episode):
    pub = interrupted_upload(db, tmp_path, episode)
    pub.hidden_finds, pub.fail = 0, None
    external_id = pub.upload(tmp_path / "toy-master.mp4", repo_package(db, tmp_path, episode)).external_id
    result = publish_resolve(db_url, monkeypatch, tmp_path, episode, "--platform", "export", "--external-id", external_id)
    assert result.exit_code == 0, result.output
    assert repo.get_episode(db, episode)["status"] == State.UPLOADED
    assert [r.external_id for r in repo.receipts(db, episode)] == [external_id]
    assert repo.get_attempt(db, episode, "export") is None
    last = repo.jobs(db, episode)[-1]
    assert (last["from_status"], last["to_status"], last["status"]) == ("ESCALATED", "UPLOADED", "succeeded")
    assert voice_runner(db, publishing_toys(pub), tmp_path).advance(episode) == State.SCHEDULED
    assert pub.uploads == 2  # the crashed attempt and the operator's stand-in; the runner uploaded nothing


def repo_package(db, tmp_path, episode) -> PublishPackage:
    row = repo.latest_artifact(db, episode, "a9_packager")
    return PublishPackage.model_validate(ArtifactStore(tmp_path).read(row["uri"])["artifact"])


def test_resolve_refuses_a_video_the_account_does_not_have(db, db_url, monkeypatch, tmp_path, episode):
    interrupted_upload(db, tmp_path, episode)
    result = publish_resolve(db_url, monkeypatch, tmp_path, episode, "--platform", "export", "--external-id", "export-nope")
    assert result.exit_code == 1 and "has no video export-nope" in result.output
    assert repo.get_episode(db, episode)["status"] == State.ESCALATED


def test_resolve_not_uploaded_clears_the_marker_and_returns_to_final_approved(db, db_url, monkeypatch, tmp_path,
                                                                              episode):
    pub = interrupted_upload(db, tmp_path, episode)
    result = publish_resolve(db_url, monkeypatch, tmp_path, episode, "--platform", "export", "--not-uploaded")
    assert result.exit_code == 0, result.output
    assert repo.get_episode(db, episode)["status"] == State.FINAL_APPROVED
    assert repo.get_attempt(db, episode, "export") is None
    pub.hidden_finds = 0
    assert voice_runner(db, publishing_toys(pub), tmp_path).advance(episode) == State.SCHEDULED
    assert pub.uploads == 2


def test_resolve_refuses_an_episode_not_escalated_at_upload(db, db_url, monkeypatch, tmp_path, episode):
    result = publish_resolve(db_url, monkeypatch, tmp_path, episode, "--platform", "export", "--not-uploaded")
    assert result.exit_code == 1 and "not escalated at c10_upload" in result.output
    both = publish_resolve(db_url, monkeypatch, tmp_path, episode, "--platform", "export", "--not-uploaded",
                   "--external-id", "x")
    assert both.exit_code == 1 and "exactly one" in both.output


def test_schedule_rerun_after_a_crash_keeps_the_quota_count(db, tmp_path, episode):
    pub = SchedulingPublisher(tmp_path / "_export")
    assert voice_runner(db, publishing_toys(pub), tmp_path).advance(episode) == State.SCHEDULED
    [scheduled] = repo.receipts(db, episode)
    # As if the process died after the receipt said scheduled but before the job moved the episode on.
    db.execute("UPDATE episode SET status = 'UPLOADED' WHERE id = %s", (episode,))
    assert voice_runner(db, publishing_toys(pub), tmp_path).advance(episode) == State.SCHEDULED
    assert repo.receipts(db, episode) == [scheduled] and pub.schedules == 1
