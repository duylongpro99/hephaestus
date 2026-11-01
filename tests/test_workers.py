"""Production workers on the xx-fixture episode: voice, visuals, composer, render, checks, publishing."""

import json
import wave
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from factory.adapters.costs import Charge, MediaError, ledger_entries
from factory.adapters.image.fake import FakeImage
from factory.adapters.llm.base import LLMError
from factory.adapters.llm.fake import FakeLLMProvider
from factory.adapters.publishing.base import PublishError
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


class PricedSpeech(FakeSpeech):
    """Fake speech that bills 0.25 a line, can fail on given call numbers, and records every request."""

    def __init__(self, pack, voices, fail_on=(), error: type[BaseException] = MediaError, **kwargs):
        super().__init__(pack, voices, **kwargs)
        self.fail_on, self.error, self.calls = set(fail_on), error, []

    def synthesize(self, request, out_path):
        self.calls.append(request)
        if len(self.calls) in self.fail_on:
            raise self.error("provider down")
        return replace(super().synthesize(request, out_path), charges=[Charge("speechco", "v1", 0.25)])


def test_a_synthesis_failure_carries_what_the_earlier_lines_billed(tmp_path, script, config, pack):
    with pytest.raises(MediaError) as failed:
        voice.voice(script, voice.direct(script, config, pack), pack, PricedSpeech(pack, VOICES, fail_on={3}),
                    tmp_path, str)
    costs = failed.value.costs
    assert [(c.station, c.vendor, c.usd) for c in costs] == [(voice.STATION, "speechco", 0.25)] * 2
    assert len({c.dedupe_key for c in costs}) == 2 and all(c.dedupe_key.startswith("c4_tts:") for c in costs)


def test_a_retry_reuses_lines_already_synthesized(tmp_path, script, config, pack):
    directives = voice.direct(script, config, pack)
    flaky = PricedSpeech(pack, VOICES, fail_on={3})
    with pytest.raises(MediaError):
        voice.voice(script, directives, pack, flaky, tmp_path / "media", str)
    manifest, charges = voice.voice(script, directives, pack, flaky, tmp_path / "media", str)
    texts = [line.text for line in script.iter_lines()]
    assert [r.text for r in flaky.calls] == texts[:3] + texts[2:]  # lines 1-2 reused, 3 onwards synthesized
    clean = PricedSpeech(pack, VOICES)
    expected, _ = voice.voice(script, directives, pack, clean, tmp_path / "clean", str)
    assert manifest.model_dump(exclude={"master_uri"}, mode="json")["lines"] == [
        {**line, "uri": line["uri"].replace("/clean/", "/media/")}
        for line in expected.model_dump(mode="json")["lines"]]
    assert (tmp_path / "media" / "master.wav").read_bytes() == (tmp_path / "clean" / "master.wav").read_bytes()
    assert len(charges) == len(texts) and len({c.dedupe_key for c in charges}) == len(texts)


def test_a_line_with_a_truncated_wav_or_missing_sidecar_is_synthesized_again(tmp_path, script, config, pack):
    directives = voice.direct(script, config, pack)
    voice.voice(script, directives, pack, FakeSpeech(pack, VOICES), tmp_path, str)
    wavs = sorted((tmp_path / "lines").glob("*.wav"))
    wavs[0].write_bytes(wavs[0].read_bytes()[:-200])  # truncated
    wavs[1].with_suffix(".json").unlink()  # killed before the sidecar was written
    sidecar = json.loads(wavs[2].with_suffix(".json").read_text())
    wavs[2].with_suffix(".json").write_text(json.dumps({**sidecar, "key": "stale"}))
    speech = PricedSpeech(pack, VOICES)
    voice.voice(script, directives, pack, speech, tmp_path, str)
    assert len(speech.calls) == 3
    assert sorted((tmp_path / "lines").glob("*.wav")) == wavs and not list((tmp_path / "lines").glob(".*.tmp"))


def test_a_changed_rate_or_voice_does_not_reuse_the_old_line(tmp_path, script, config, pack):
    directives = voice.direct(script, config, pack)
    voice.voice(script, directives, pack, FakeSpeech(pack, VOICES), tmp_path, str)
    slower = directives.model_copy(update={"lines": [
        directives.lines[0].model_copy(update={"rate": directives.lines[0].rate * 0.9}), *directives.lines[1:]]})
    speech = PricedSpeech(pack, VOICES)
    voice.voice(script, slower, pack, speech, tmp_path, str)
    assert [r.text for r in speech.calls] == [next(script.iter_lines()).text]
    other_voices = PricedSpeech(pack, {"xx-a": "fake-c", "xx-b": "fake-b"})
    voice.voice(script, directives, pack, other_voices, tmp_path, str)
    assert len(other_voices.calls) == len(directives.lines)  # the identity is part of every line's key


def test_the_manifest_charges_every_line_once_including_reused_ones(tmp_path, script, config, pack):
    directives = voice.direct(script, config, pack)
    first, first_charges = voice.voice(script, directives, pack, PricedSpeech(pack, VOICES), tmp_path, str)
    reused = PricedSpeech(pack, VOICES)
    _, charges = voice.voice(script, directives, pack, reused, tmp_path, str)
    assert reused.calls == [] and charges == first_charges
    entries = ledger_entries(voice.STATION, charges)
    assert len(entries) == len(directives.lines) and sum(e.usd for e in entries) == 0.25 * len(directives.lines)


def test_a_rate_outside_the_synthesizer_range_fails_before_any_request(tmp_path, script, config, pack):
    directives = voice.direct(script, config, pack)
    fast = directives.model_copy(update={"lines": [
        *directives.lines[:-1], directives.lines[-1].model_copy(update={"rate": pack.native_rate * 9})]})
    speech = PricedSpeech(pack, VOICES)
    with pytest.raises(voice.RateOutOfRange, match=f"{directives.lines[-1].line_id} at 9.00") as failed:
        voice.voice(script, fast, pack, speech, tmp_path, str)
    assert speech.calls == [] and failed.value.costs == []


class CountingPublisher(ExportPublisher):
    """The export publisher, counting uploads; `fail` raises in the next upload, before or after the copy."""

    def __init__(self, out_dir, fail: Exception | None = None, after_copy: bool = False, hidden_finds: int = 0):
        super().__init__(out_dir)
        self.uploads, self.finds, self.fail, self.after_copy, self.hidden_finds = 0, 0, fail, after_copy, hidden_finds

    def upload(self, video, package):
        self.uploads += 1
        fail, self.fail = self.fail, None
        if fail and not self.after_copy:
            raise fail
        done = super().upload(video, package)
        if fail:
            raise fail
        return done

    def find(self, episode_id):
        """Like a platform that lists a new upload late: the first `hidden_finds` lookups see nothing."""
        self.finds += 1
        if self.finds <= self.hidden_finds:
            return None, 1
        found, _ = super().find(episode_id)
        return found, 1


class MemoryRecords:
    def __init__(self, receipt=None, attempt=None):
        self.stored, self.started, self.finished_together = receipt, attempt, False

    def receipt(self):
        return self.stored

    def attempt(self):
        return self.started

    def start(self, at):
        assert self.started is None
        self.started = at

    def clear(self):
        self.started = None

    def finish(self, receipt):
        self.stored, self.started, self.finished_together = receipt, None, True


class StepClock:
    def __init__(self):
        self.t, self.sleeps = datetime(2026, 10, 22, 9, 30, tzinfo=timezone.utc), []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)


@pytest.fixture
def publishable(tmp_path, spec, config, script, produced):
    _, _, _, _, props, video = produced
    copy, _ = packaging.write_copy(spec, script, config, FakeLLMProvider(EPISODE))
    return video, packaging.package(spec, config, props, "video.mp4", copy)


def test_publisher_refuses_a_second_upload(tmp_path, publishable):
    video, package = publishable
    pub, clock, records = CountingPublisher(tmp_path), StepClock(), MemoryRecords()
    receipt = publisher.upload(records, pub, video, package, clock)
    again = publisher.upload(records, pub, video, package, clock)
    assert again == receipt and pub.uploads == 1 and receipt.upload_ts == clock.t
    publish_at = publisher.publish_time(package, clock.t)
    assert publish_at == datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
    assert publisher.schedule(receipt, pub, publish_at, package).status == "scheduled"


def test_success_writes_the_receipt_and_clears_the_marker_together(tmp_path, publishable):
    video, package = publishable
    records = MemoryRecords()

    class Watching(CountingPublisher):
        def upload(self, video, package):
            assert records.started is not None, "the marker is written before the upload begins"
            return super().upload(video, package)

    receipt = publisher.upload(records, Watching(tmp_path), video, package, StepClock())
    assert records.finished_together and records.stored == receipt and records.started is None


def test_an_error_before_any_bytes_clears_the_marker_and_retries(tmp_path, publishable):
    video, package = publishable
    records, refused = MemoryRecords(), PublishError("quota exhausted", video_may_exist=False)
    pub = CountingPublisher(tmp_path, fail=refused)
    with pytest.raises(PublishError, match="quota"):
        publisher.upload(records, pub, video, package, StepClock())
    assert records.started is None
    assert publisher.upload(records, pub, video, package, StepClock()).external_id.startswith("export-")
    assert pub.uploads == 2 and pub.finds == 0


def test_an_error_mid_upload_keeps_the_marker(tmp_path, publishable):
    video, package = publishable
    records = MemoryRecords()
    pub = CountingPublisher(tmp_path, fail=PublishError("connection reset"), after_copy=True)
    with pytest.raises(PublishError, match="connection reset"):
        publisher.upload(records, pub, video, package, StepClock())
    assert records.started is not None and records.stored is None
    receipt = publisher.upload(records, pub, video, package, StepClock())  # found, not uploaded again
    assert pub.uploads == 1 and receipt.external_id == pub.find(package.episode_id)[0]
    assert receipt.quota_units == 1 and records.started is None


def test_a_marker_without_a_video_escalates_after_polling(tmp_path, publishable):
    video, package = publishable
    started = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
    records, pub, clock = MemoryRecords(attempt=started), CountingPublisher(tmp_path), StepClock()
    with pytest.raises(publisher.UploadUnconfirmed, match="2026-10-22T09:00:00.*factory publish resolve"):
        publisher.upload(records, pub, video, package, clock)
    assert pub.uploads == 0 and pub.finds == publisher.MARKER_POLLS
    assert clock.sleeps == [publisher.MARKER_POLL_INTERVAL_S] * (publisher.MARKER_POLLS - 1)
    assert records.started == started and records.stored is None


def test_a_late_listed_video_is_found_while_polling(tmp_path, publishable):
    video, package = publishable
    ExportPublisher(tmp_path).upload(video, package)  # the upload went through, then the process died
    records = MemoryRecords(attempt=datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc))
    pub, clock = CountingPublisher(tmp_path, hidden_finds=2), StepClock()
    receipt = publisher.upload(records, pub, video, package, clock)
    assert pub.uploads == 0 and receipt.quota_units == 3 and len(clock.sleeps) == 2
    assert records.finished_together


def test_ids_that_would_escape_the_media_folder_are_refused(tmp_path, script, config, pack):
    bad = script.model_copy(deep=True)
    bad.segments[0].lines[0].id = "../../x"
    directives = voice.direct(bad, config, pack)
    with pytest.raises(ValueError, match="cannot name a file"):
        voice.voice(bad, directives, pack, FakeSpeech(pack, VOICES), tmp_path, str)


def test_tags_length_counts_commas_and_quotes_for_spaces():
    assert compliance.tags_length([]) == 0
    assert compliance.tags_length(["abc"]) == 3
    assert compliance.tags_length(["abc", "de"]) == 6  # one comma
    assert compliance.tags_length(["two words", "x"]) == 9 + 2 + 1 + 1


def test_compliance_counts_the_episode_tag_against_the_tag_limit(spec, config, publishable):
    _, package = publishable
    room = compliance.TAGS_MAX - 1  # one comma before the episode tag
    fits = package.model_copy(update={"tags": {lang: ["x" * (room - len(f"ep-{spec.episode_id}"))]
                                               for lang in package.title}})
    assert compliance.check(fits, config).hard_gate_failures == []
    full = package.model_copy(update={"tags": {lang: ["x" * compliance.TAGS_MAX] for lang in package.title}})
    assert compliance.tags_length(full.tags["en"]) == compliance.TAGS_MAX  # fine on its own
    failures = compliance.check(full, config).hard_gate_failures
    assert any("with the episode tag" in f for f in failures)


class SchedulingPublisher(CountingPublisher):
    def __init__(self, out_dir):
        super().__init__(out_dir)
        self.schedules = 0

    def schedule(self, external_id, publish_at, package):
        self.schedules += 1
        super().schedule(external_id, publish_at, package)
        return 51


def test_rescheduling_an_already_scheduled_receipt_spends_no_quota(tmp_path, publishable):
    video, package = publishable
    pub, clock = SchedulingPublisher(tmp_path), StepClock()
    receipt = publisher.upload(MemoryRecords(), pub, video, package, clock)
    at = publisher.publish_time(package, clock.t)
    scheduled = publisher.schedule(receipt, pub, at, package)
    assert publisher.schedule(scheduled, pub, at, package) == scheduled
    assert pub.schedules == 1 and scheduled.quota_units == receipt.quota_units + 51


def test_a_receipt_scheduled_at_another_time_is_scheduled_again(tmp_path, publishable):
    video, package = publishable
    pub, clock = SchedulingPublisher(tmp_path), StepClock()
    receipt = publisher.upload(MemoryRecords(), pub, video, package, clock)
    at = publisher.publish_time(package, clock.t)
    scheduled = publisher.schedule(receipt, pub, at, package)
    moved = publisher.schedule(scheduled, pub, at.replace(hour=at.hour + 1), package)
    assert pub.schedules == 2 and moved.publish_at.hour == at.hour + 1


def test_two_lines_with_the_same_text_are_two_charges(tmp_path, script, config, pack):
    repeated = script.model_copy(deep=True)
    first, second = list(repeated.iter_lines())[:2]
    second.text = first.text
    directives = voice.direct(repeated, config, pack)
    same = directives.lines[0]
    directives.lines[1] = directives.lines[1].model_copy(update={"voice": same.voice, "rate": same.rate})
    speech = PricedSpeech(pack, VOICES)
    _, charges = voice.voice(repeated, directives, pack, speech, tmp_path, str)
    assert speech.calls[0] == speech.calls[1]  # same text, voice and rate: the same audio key
    assert len(speech.calls) == len(charges) == len(directives.lines)
    assert len({c.dedupe_key for c in charges}) == len(charges)
