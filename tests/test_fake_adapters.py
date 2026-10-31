"""Fake vendors: deterministic, network-free, and shaped like the real adapter protocols."""

import json
import wave

import pytest
from pydantic import BaseModel

from factory.adapters.image.fake import FakeImageProvider
from factory.adapters.llm.base import LLMError, LLMProvider
from factory.adapters.llm.fake import FakeLLMProvider
from factory.adapters.publish.fake import FakePublisher
from factory.adapters.tts.fake import FakeTTS
from factory.agents.review_panel.agent import PanelVerdict
from factory.contracts import PublishPackage
from factory.tools.language_pack import load_pack
from tests.conftest import FIXTURES

XX_FIXTURES = FIXTURES / "xx-fixture" / "xx-A2-e2e"


@pytest.fixture(scope="module")
def pack():
    return load_pack("xx-fixture")


def test_tts_length_follows_speech_units_and_rate(tmp_path, pack):
    tts = FakeTTS(pack)
    seconds = tts.synthesize("Mi pa ko e te.", "fake-a", 120.0, tmp_path / "a.wav")
    assert seconds == pytest.approx(5 / 120 * 60)
    with wave.open(str(tmp_path / "a.wav")) as wav:
        assert wav.getnchannels() == 1 and wav.getnframes() / wav.getframerate() == pytest.approx(seconds)


def test_tts_is_deterministic(tmp_path, pack):
    tts = FakeTTS(pack)
    for name in ("a.wav", "b.wav"):
        tts.synthesize("Ya, mi lu ko!", "fake-b", 110.0, tmp_path / name)
    assert (tmp_path / "a.wav").read_bytes() == (tmp_path / "b.wav").read_bytes()


def test_image_is_a_deterministic_png_per_prompt(tmp_path):
    images = FakeImageProvider()
    images.generate("cafe", 1920, 1080, tmp_path / "a.png")
    images.generate("cafe", 1920, 1080, tmp_path / "b.png")
    images.generate("street", 1920, 1080, tmp_path / "c.png")
    a = (tmp_path / "a.png").read_bytes()
    assert a.startswith(b"\x89PNG") and a == (tmp_path / "b.png").read_bytes()
    assert a != (tmp_path / "c.png").read_bytes()
    from PIL import Image

    with Image.open(tmp_path / "a.png") as img:
        assert img.size == (1920, 1080)


def package(episode_id="e1") -> PublishPackage:
    return PublishPackage(episode_id=episode_id, video_uri="v.mp4", title={"en": "t"}, description={"en": "d"},
                          tags={"en": []}, chapters=[], made_for_kids=False, contains_synthetic_media=True)


def test_publisher_id_comes_from_the_file(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    publisher = FakePublisher(tmp_path / "out")
    first, second = publisher.upload(video, package()), publisher.upload(video, package())
    assert first.external_id == second.external_id and first.external_id.startswith("fake-")
    from datetime import datetime, timezone

    publisher.schedule(first.external_id, datetime(2026, 11, 1, tzinfo=timezone.utc))
    meta = json.loads((tmp_path / "out" / f"{first.external_id}.json").read_text())
    assert meta["privacy"] == "private" and meta["publish_at"].startswith("2026-11-01")


def test_fake_llm_validates_its_fixture():
    llm: LLMProvider = FakeLLMProvider(XX_FIXTURES)
    result = llm.structured(station="review_examiner", system=[], user="", output_model=PanelVerdict)
    assert result.parsed.decision == "approve"
    assert [(c.vendor, c.usd, c.priced) for c in result.costs] == [("fake", 0.0, True)]

    class Other(BaseModel):
        something_else: int

    with pytest.raises(LLMError, match="does not match"):
        llm.structured(station="review_examiner", system=[], user="", output_model=Other)
    with pytest.raises(LLMError, match="no fixture"):
        llm.structured(station="nobody", system=[], user="", output_model=Other)


def test_fake_llm_identity_tracks_fixture_contents(tmp_path):
    (tmp_path / "s.json").write_text("{}")
    before = FakeLLMProvider(tmp_path).identity
    (tmp_path / "s.json").write_text('{"a": 1}')
    assert FakeLLMProvider(tmp_path).identity != before


def test_fake_llm_replays_tool_calls(tmp_path):
    from factory.adapters.llm.base import ToolSpec

    class Args(BaseModel):
        word: str

    seen = []
    tool = ToolSpec("note", "remember a word", Args, lambda a: seen.append(a.word) or "ok")
    (tmp_path / "editor.json").write_text(json.dumps([{"name": "note", "arguments": {"word": "kosa"}}]))
    FakeLLMProvider(tmp_path).tool_loop(station="editor", system=[], user="", tools=[tool])
    assert seen == ["kosa"]
