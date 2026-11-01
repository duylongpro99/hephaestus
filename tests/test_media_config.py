"""config/media.yaml: profiles pick one provider per purpose, voices map, secrets come from the environment."""

import pytest
import yaml
from pydantic import ValidationError

from factory.adapters import media
from factory.adapters.costs import Charge, MediaError, MediaPrice, charge, ledger_entries
from factory.config import check_cast_voices, resolve
from factory.tools.language_pack import load_pack


def config(**changes) -> media.MediaConfig:
    """The repo's media config with `changes` applied, each keyed by a dotted path."""
    data = yaml.safe_load(media.MEDIA_CONFIG_PATH.read_text(encoding="utf-8"))
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        node = data
        for key in parents:
            node = node[key]
        node[leaf] = value
    return media.MediaConfig.model_validate(data)


def test_the_repo_config_loads_and_the_fake_profile_serves_every_purpose(tmp_path):
    loaded = media.load_media_config()
    for code in ("en", "xx-fixture"):
        assert media.speech_for("fake", load_pack(code), loaded).identity.startswith("fake_speech/")
    assert media.image_for("fake", loaded).identity.startswith("fake_image/")
    assert media.video_for("fake", load_pack("en"), loaded).identity.startswith("ffmpeg_pillow/")
    publisher = media.publisher_for("fake", tmp_path, loaded)
    assert publisher.platform == "export" and publisher.out_dir == tmp_path / "_export"


def test_a_pack_voice_without_a_provider_voice_is_refused():
    loaded = config(**{"profiles.fake.speech.voices": {"xx-a": "fake-a"}})
    with pytest.raises(MediaError, match="no provider voice for xx-b"):
        media.speech_for("fake", load_pack("xx-fixture"), loaded)


def test_an_unknown_profile_names_the_ones_there_are():
    with pytest.raises(MediaError, match="profiles: fake"):
        media.image_for("nope", media.load_media_config())


def test_a_profile_cannot_use_an_undefined_provider_or_one_of_another_purpose():
    with pytest.raises(ValidationError, match="undefined provider 'missing'"):
        config(**{"profiles.fake.image.provider": "missing"})
    with pytest.raises(ValidationError, match="image provider 'export' is a publishing provider"):
        config(**{"profiles.fake.image.provider": "export"})


def test_unknown_keys_are_refused():
    with pytest.raises(ValidationError):
        config(**{"providers.export.dir": "elsewhere"})


def test_a_missing_secret_names_the_variable(monkeypatch):
    loaded = config(**{"providers.real": {"type": "deepinfra", "model": "m", "env": {"key": "TEST_MEDIA_KEY"}},
                       "profiles.fake.image.provider": "real"})
    monkeypatch.delenv("TEST_MEDIA_KEY", raising=False)
    with pytest.raises(MediaError, match=r"\$TEST_MEDIA_KEY is not set \(the key for media provider real\)"):
        media.image_for("fake", loaded)


def test_the_profile_defaults_to_fake_unless_the_environment_names_one(monkeypatch):
    monkeypatch.delenv(media.PROFILE_ENV, raising=False)
    assert media.default_profile() == "fake"
    monkeypatch.setenv(media.PROFILE_ENV, "live")
    assert media.default_profile() == "live"


def test_charges_merge_per_vendor_and_model():
    price = MediaPrice(usd=16.0, per=1_000_000)
    charges = [charge("v", "m", 500_000, price), charge("v", "m", 250_000, price), charge("v", "other", 3, None)]
    entries = ledger_entries("c4_tts", charges)
    assert [(e.station, e.model, e.usd, e.priced) for e in entries] == [
        ("c4_tts", "m", 12.0, True), ("c4_tts", "other", 0.0, False)]
    assert ledger_entries("c4_tts", [Charge("v", "m", 1.0), Charge("v", "m", 0.0, priced=False)])[0].priced is False


def test_channels_cast_only_voices_their_pack_offers():
    bible = resolve("en-podcast-spike", "A2").channel
    assert {m.id: m.voice for m in bible.cast} == {"anna": "en-gb-female-1", "ben": "en-gb-male-1"}
    bad = bible.model_copy(update={"cast": [bible.cast[0].model_copy(update={"voice": "fr-fr-female-1"})]})
    with pytest.raises(ValueError, match="anna: fr-fr-female-1"):
        check_cast_voices(bad, [v.key for v in load_pack("en").voices])
