"""The runner against Postgres, with toy stations: jobs, artifacts, retries, budget, gates and resume."""

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from factory.adapters.costs import MediaError
from factory.artifacts import ArtifactStore, Built
from factory.config import resolve
from factory.contracts import CostEntry, EpisodeSpec, GateDecision, QAReport
from factory.orchestrator import repo
from factory.orchestrator.runner import Runner, StationResult
from factory.orchestrator.states import PIPELINE, State
from tests.test_workers import SPEC_PATH

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


def test_panel_rejects_once_then_escalates(db, tmp_path, episode):
    toys = Toys()
    toys.outcome["review_panel"] = "reject"
    assert runner(db, toys, tmp_path).advance(episode) == State.ESCALATED
    panel_jobs = [(j["status"], j["to_status"]) for j in repo.jobs(db, episode) if j["station"] == "review_panel"]
    assert panel_jobs == [("rejected", "DRAFTED"), ("escalated", "ESCALATED")]


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
