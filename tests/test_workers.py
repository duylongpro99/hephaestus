"""Production workers on the xx-fixture episode: voice, visuals, composer, render, checks, publishing."""

import json
import wave
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from factory.adapters.costs import Charge, MediaError
from factory.adapters.image.fake import FakeImage
from factory.adapters.llm.base import LLMError
from factory.adapters.llm.fake import FakeLLMProvider
from factory.adapters.publishing.export import ExportPublisher
from factory.adapters.speech.fake import FakeSpeech
from factory.adapters.video.ffmpeg_pillow import FFmpegPillowRenderer
from factory.agents.drafts import draft_models, to_script
from factory.artifacts import ArtifactStore, canonical
from factory.config import resolve
from factory.contracts import EpisodeSpec
from factory.tools.enrichment import enrich
from factory.tools.language_pack import load_pack
from factory.workers import compliance, composer, packaging, publisher, tech_checks, visuals, voice
from tests.adapters import conformance
from tests.conftest import FIXTURES

EPISODE = FIXTURES / "xx-fixture" / "xx-A2-e2e"
SPEC_PATH = FIXTURES.parent.parent / "evals" / "xx-fixture" / "adult" / "specs" / "xx-A2-e2e.json"
VOICES = {"xx-a": "fake-a", "xx-b": "fake-b"}


@pytest.fixture(scope="module")
def spec():
    return EpisodeSpec.model_validate_json(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config(spec):
    return resolve(spec.channel, spec.level)


@pytest.fixture(scope="module")
def pack():
    return load_pack("xx-fixture")


@pytest.fixture(scope="module")
def script(spec):
    draft = draft_models("xx-fixture", ("en",)).model_validate_json((EPISODE / "a2_scriptwriter.json").read_text())
    return to_script(draft, spec.episode_id, "xx-fixture", ["en"])


@pytest.fixture(scope="module")
def produced(tmp_path_factory, script, config, pack):
    """Audio, shots, props and the rendered video, made once for the module."""
    store = ArtifactStore(tmp_path_factory.mktemp("store"))
    directives = voice.direct(script, config, pack)
    audio, voice_charges = voice.voice(script, directives, pack, FakeSpeech(pack, VOICES), store.root / "audio",
                                       store.uri)
    shots, image_charges = visuals.shoot(script, config, FakeImage(), store.root / "shots", store.uri)
    assert voice_charges == image_charges == []
    props = composer.compose(script, audio, shots)
    video = conformance.check_video(FFmpegPillowRenderer(), props, store.resolve, store.root / "render")
    return store, directives, audio, shots, props, video


def test_enrichment_is_empty_for_a_pack_without_reading_aids(script, pack):
    assert enrich(script, pack, "A2").lines == []


def test_voice_directives_follow_cast_and_band(produced, script, config):
    _, directives, *_ = produced
    assert [d.line_id for d in directives.lines] == [line.id for line in script.iter_lines()]
    assert {d.speaker: d.voice for d in directives.lines} == {"kira": "xx-a", "tomo": "xx-b"}
    assert all(d.rate == config.band.rate.midpoint and d.variant == "natural" for d in directives.lines)


def test_master_track_is_lines_plus_pauses(produced):
    store, _, audio, *_ = produced
    with wave.open(str(store.resolve(audio.master_uri))) as wav:
        seconds = wav.getnframes() / wav.getframerate()
    assert seconds == pytest.approx(audio.total_duration_s, abs=0.01)
    last = audio.lines[-1]
    assert last.start_s + last.duration_s + last.pause_after_s == pytest.approx(audio.total_duration_s, abs=0.001)


def test_composer_is_pure_and_deterministic(produced, script):
    _, _, audio, shots, props, _ = produced
    again = composer.compose(script.model_copy(deep=True), audio.model_copy(deep=True), shots.model_copy(deep=True))
    assert canonical(again) == canonical(props)
    assert [c.line_id for s in props.scenes for c in s.captions] == [line.id for line in script.iter_lines()]
    assert props.scenes[0].start_s == 0 and props.total_duration_s == audio.total_duration_s


def test_render_passes_tech_checks(produced):
    _, _, audio, _, props, video = produced
    report = tech_checks.check(video, audio, props.width, props.height)
    assert report.hard_gate_failures == [], report.summary


def test_tech_checks_catch_a_wrong_duration_and_size(produced):
    _, _, audio, _, props, video = produced
    longer = audio.model_copy(update={"total_duration_s": audio.total_duration_s * 2})
    failures = tech_checks.check(video, longer, 1280, 720).hard_gate_failures
    assert any("expected 1280x720" in f for f in failures) and any("duration" in f for f in failures)


def test_packager_fills_flags_and_chapters(spec, config, script, produced):
    _, _, _, _, props, _ = produced
    copy, costs = packaging.write_copy(spec, script, config, FakeLLMProvider(EPISODE))
    package = packaging.package(spec, config, props, "video.mp4", copy)
    assert package.title["en"] and package.made_for_kids is False and package.contains_synthetic_media
    assert [c.start_s for c in package.chapters] == [0]
    assert compliance.check(package, config).hard_gate_failures == []


def test_packager_requires_copy_in_every_support_language(tmp_path, spec, config, script):
    fixture = json.loads((EPISODE / "a9_packager.json").read_text())
    fixture["copies"][0]["language"] = "vi"
    (tmp_path / "a9_packager.json").write_text(json.dumps(fixture))
    with pytest.raises(LLMError, match="no copy for en"):
        packaging.write_copy(spec, script, config, FakeLLMProvider(tmp_path))


def test_compliance_flags_a_wrong_made_for_kids(spec, config, script, produced):
    _, _, _, _, props, _ = produced
    copy, _ = packaging.write_copy(spec, script, config, FakeLLMProvider(EPISODE))
    package = packaging.package(spec, config, props, "video.mp4", copy).model_copy(
        update={"made_for_kids": True, "contains_synthetic_media": False})
    failures = compliance.check(package, config).hard_gate_failures
    assert any("made_for_kids" in f for f in failures) and any("synthetic" in f for f in failures)


def test_the_channel_bible_picks_a_cast_voice_over_cast_order(script, config, pack):
    cast = [config.channel.cast[0].model_copy(update={"voice": "xx-b"}), config.channel.cast[1]]
    swapped = config.model_copy(update={"channel": config.channel.model_copy(update={"cast": cast})})
    directives = voice.direct(script, swapped, pack)
    assert {d.speaker: d.voice for d in directives.lines} == {"kira": "xx-b", "tomo": "xx-b"}


def test_the_synthesizer_gets_the_rate_relative_to_the_native_rate(tmp_path, script, config, pack):
    seen = []

    class Recording(FakeSpeech):
        def synthesize(self, request, out_path):
            seen.append(request)
            return super().synthesize(request, out_path)

    directives = voice.direct(script, config, pack)
    voice.voice(script, directives, pack, Recording(pack, VOICES), tmp_path, str)
    assert [r.rate for r in seen] == [d.rate / pack.native_rate for d in directives.lines]
    assert {r.language for r in seen} == {"xx-fixture"}


def test_a_synthesis_failure_carries_what_the_earlier_lines_billed(tmp_path, script, config, pack):
    calls = []

    class FailsOnThird(FakeSpeech):
        def synthesize(self, request, out_path):
            calls.append(request)
            if len(calls) == 3:
                raise MediaError("provider down")
            result = super().synthesize(request, out_path)
            return replace(result, charges=[Charge("speechco", "v1", 0.25)])

    with pytest.raises(MediaError) as failed:
        voice.voice(script, voice.direct(script, config, pack), pack, FailsOnThird(pack, VOICES), tmp_path, str)
    assert [(c.station, c.vendor, c.usd) for c in failed.value.costs] == [(voice.STATION, "speechco", 0.5)]


class CountingPublisher(ExportPublisher):
    def __init__(self, out_dir):
        super().__init__(out_dir)
        self.uploads = 0

    def upload(self, video, package):
        self.uploads += 1
        return super().upload(video, package)


def test_publisher_refuses_a_second_upload(tmp_path, spec, config, script, produced):
    _, _, _, _, props, video = produced
    copy, _ = packaging.write_copy(spec, script, config, FakeLLMProvider(EPISODE))
    package = packaging.package(spec, config, props, "video.mp4", copy)
    pub, now = CountingPublisher(tmp_path), datetime(2026, 10, 22, 9, 30, tzinfo=timezone.utc)
    receipt, uploaded = publisher.upload(None, pub, video, package, now)
    again, uploaded_again = publisher.upload(receipt, pub, video, package, now)
    assert uploaded and not uploaded_again and again == receipt and pub.uploads == 1
    publish_at = publisher.publish_time(package, now)
    assert publish_at == datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
    assert publisher.schedule(receipt, pub, publish_at, package).status == "scheduled"


def test_ids_that_would_escape_the_media_folder_are_refused(tmp_path, script, config, pack):
    bad = script.model_copy(deep=True)
    bad.segments[0].lines[0].id = "../../x"
    directives = voice.direct(bad, config, pack)
    with pytest.raises(ValueError, match="cannot name a file"):
        voice.voice(bad, directives, pack, FakeSpeech(pack, VOICES), tmp_path, str)
