"""One xx-fixture episode from SPEC to SCHEDULED through the real stations, with fake vendors."""

import json
from functools import cache

import pytest
from typer.testing import CliRunner

from factory.adapters import media
from factory.adapters.llm.fake import FakeLLMProvider
from factory.artifacts import ArtifactStore
from factory.cli import app
from factory.contracts import AudioManifest, RenderedVideo
from factory.orchestrator import repo
from factory.orchestrator.db import connect
from factory.orchestrator.runner import Runner
from factory.orchestrator.stations import Stations, Vendors, file_sha256
from factory.orchestrator.states import PIPELINE, State
from factory.workers import tech_checks
from tests.test_workers import EPISODE, SPEC_PATH, CountingPublisher

pytestmark = pytest.mark.e2e


@pytest.fixture
def ran(db_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)
    result = CliRunner().invoke(app, ["run", str(SPEC_PATH), "--auto-approve", "--fake-llm", "--artifacts", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return ArtifactStore(tmp_path), json.loads(SPEC_PATH.read_text())["episode_id"]


def test_episode_reaches_scheduled_with_a_job_per_transition(ran, db):
    _, episode = ran
    assert repo.get_episode(db, episode)["status"] == State.SCHEDULED
    moves = [(j["from_status"], j["to_status"]) for j in repo.jobs(db, episode)]
    assert moves == [(s.value, step.next.value) for s, step in PIPELINE.items()]


def test_every_artifact_row_matches_the_store(ran, db):
    store, episode = ran
    rows = repo.artifacts(db, episode)
    assert {r["station"] for r in rows} >= {"a2_scriptwriter", "a3_level_editor", "c5_audio", "c8_render",
                                             "a9_packager", "c10_upload", "c10_schedule"}
    for row in rows:
        envelope = store.read(row["uri"])
        assert envelope["hash"] == row["hash"] and envelope["station_version"] == row["station_version"]
    video = RenderedVideo.model_validate(store.read(repo.latest_artifact(db, episode, "c8_render")["uri"])["artifact"])
    assert file_sha256(store.resolve(video.uri)) == video.sha256


def test_master_mp4_passes_c9(ran, db):
    store, episode = ran
    video = RenderedVideo.model_validate(store.read(repo.latest_artifact(db, episode, "c8_render")["uri"])["artifact"])
    audio = AudioManifest.model_validate(store.read(repo.latest_artifact(db, episode, "c5_audio")["uri"])["artifact"])
    path = store.resolve(video.uri)
    assert path.name == "master.mp4"
    assert tech_checks.check(path, audio, 1920, 1080).hard_gate_failures == []


def test_receipt_is_stored_and_a_rerun_does_not_upload_again(ran, db_url, tmp_path):
    store, episode = ran
    with connect(db_url) as conn:
        [receipt] = repo.receipts(conn, episode)
        assert receipt.status == "scheduled" and receipt.publish_at is not None
        # Force the publish steps to run again, as after a crash between upload and scheduling.
        conn.execute("UPDATE episode SET status = 'FINAL_APPROVED' WHERE id = %s", (episode,))
        publisher = CountingPublisher(store.root / "_export")

        @cache
        def llm(role):
            return FakeLLMProvider(EPISODE)

        vendors = Vendors(llm=llm, speech=lambda pack: media.speech_for("fake", pack), images=media.image_for("fake"),
                          video=lambda pack: media.video_for("fake", pack), publisher=publisher)
        assert Runner(conn, Stations(vendors).registry(), store).advance(episode) == State.SCHEDULED
        assert publisher.uploads == 0
        assert repo.receipts(conn, episode) == [receipt]
