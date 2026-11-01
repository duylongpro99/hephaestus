"""The offline providers of the fake profile: deterministic, network-free and conformant."""

import json
import wave
from datetime import datetime, timezone

import pytest
from PIL import Image

from factory.adapters.image.base import ImageRequest, fit_image
from factory.adapters.image.fake import FakeImage
from factory.adapters.publishing.base import PublishError
from factory.adapters.publishing.export import ExportPublisher
from factory.adapters.speech.base import SpeechRequest
from factory.adapters.speech.fake import FakeSpeech
from factory.contracts import PublishPackage
from factory.tools.language_pack import load_pack
from tests.adapters import conformance

VOICES = {"xx-a": "fake-a", "xx-b": "fake-b"}


@pytest.fixture(scope="module")
def pack():
    return load_pack("xx-fixture")


def request(text="Mi pa ko e te.", voice="xx-a", rate=0.8) -> SpeechRequest:
    return SpeechRequest(text=text, language="xx-fixture", voice=voice, rate=rate)


def test_speech_conforms_and_its_length_follows_speech_units_and_rate(tmp_path, pack):
    result = conformance.check_speech(FakeSpeech(pack, VOICES), request(), tmp_path / "a.wav")
    assert result.duration_s == pytest.approx(5 / (0.8 * pack.native_rate) * 60)
    assert result.words is None and result.charges == []


def test_speech_is_deterministic_and_voices_differ(tmp_path, pack):
    speech = FakeSpeech(pack, VOICES)
    for name, voice in (("a.wav", "xx-b"), ("b.wav", "xx-b"), ("c.wav", "xx-a")):
        speech.synthesize(request("Ya, mi lu ko!", voice), tmp_path / name)
    assert (tmp_path / "a.wav").read_bytes() == (tmp_path / "b.wav").read_bytes()
    assert (tmp_path / "a.wav").read_bytes() != (tmp_path / "c.wav").read_bytes()


def test_speech_identity_follows_the_voice_mapping_and_sample_rate(tmp_path, pack):
    base = FakeSpeech(pack, VOICES)
    assert FakeSpeech(pack, {**VOICES, "xx-a": "fake-c"}).identity != base.identity
    other_rate = FakeSpeech(pack, VOICES, sample_rate=16_000)
    assert other_rate.identity != base.identity
    other_rate.synthesize(request(), tmp_path / "a.wav")
    with wave.open(str(tmp_path / "a.wav")) as wav:
        assert wav.getframerate() == 16_000


def test_image_conforms_and_is_deterministic_per_prompt(tmp_path):
    images = FakeImage()
    conformance.check_image(images, ImageRequest.for_prompt("cafe", 1920, 1080), tmp_path / "a.png")
    images.generate(ImageRequest.for_prompt("cafe", 1920, 1080), tmp_path / "b.png")
    images.generate(ImageRequest.for_prompt("street", 1920, 1080), tmp_path / "c.png")
    a = (tmp_path / "a.png").read_bytes()
    assert a == (tmp_path / "b.png").read_bytes() and a != (tmp_path / "c.png").read_bytes()


def test_image_seed_comes_from_the_prompt():
    assert ImageRequest.for_prompt("cafe", 8, 8).seed == ImageRequest.for_prompt("cafe", 16, 16).seed
    assert ImageRequest.for_prompt("cafe", 8, 8).seed != ImageRequest.for_prompt("street", 8, 8).seed


def test_fit_image_crops_to_the_frame(tmp_path):
    from io import BytesIO

    square = Image.new("RGB", (1024, 1024), "red")
    square.paste(Image.new("RGB", (1024, 100), "blue"), (0, 0))  # a band the 16:9 centre crop cuts away
    data = BytesIO()
    square.save(data, format="JPEG")
    fit_image(data.getvalue(), 1920, 1080, tmp_path / "out.png")
    with Image.open(tmp_path / "out.png") as img:
        assert img.size == (1920, 1080) and img.format == "PNG"
        r, g, b = img.getpixel((960, 5))
        assert r > 200 and b < 60


def test_fit_image_refuses_bytes_that_are_not_an_image(tmp_path):
    from factory.adapters.image.base import ImageError

    with pytest.raises(ImageError, match="not an image"):
        fit_image(b"<html>quota exceeded</html>", 8, 8, tmp_path / "x.png")


def package(episode_id="e1") -> PublishPackage:
    return PublishPackage(episode_id=episode_id, video_uri="v.mp4", title={"en": "t"}, description={"en": "d"},
                          tags={"en": []}, chapters=[], made_for_kids=False, contains_synthetic_media=True)


def test_export_conforms_and_its_id_comes_from_the_file(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    publisher = ExportPublisher(tmp_path / "out")
    external_id = conformance.check_publisher(publisher, video, package())
    assert external_id.startswith("export-") and publisher.upload(video, package()).external_id == external_id
    meta = json.loads((tmp_path / "out" / f"{external_id}.json").read_text())
    assert meta["privacy"] == "private" and meta["publish_at"].startswith("2030-01-01")


def test_export_cannot_schedule_what_it_never_exported(tmp_path):
    with pytest.raises(PublishError, match="no exported video"):
        ExportPublisher(tmp_path).schedule("export-missing", datetime(2030, 1, 1, tzinfo=timezone.utc), package())
