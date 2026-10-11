import pytest

from factory.config import resolve
from factory.contracts import EpisodeSpec, Script
from factory.tools.language_pack import load_pack
from factory.tools.profiler import format_report, profile
from tests.conftest import load_fixture

CLEAN_LINES = [
    "I want to buy a cheap coffee this morning.",
    "The coffee at the small shop is very cheap.",
    "My friend Ben says the big shop is not cheap.",
    "We walk to the cheap shop near the old station.",
    "The food there is good and the tea is cheap.",
    "I think a cheap breakfast is a good way to start.",
]


@pytest.fixture(scope="module")
def pack():
    return load_pack("en")


@pytest.fixture(scope="module")
def config():
    return resolve("en-podcast-spike", "A2")


def make_spec(length=(0.3, 1.0)) -> EpisodeSpec:
    data = load_fixture("spec_example.json") | {"target_words": ["cheap"], "review_words": [], "length_min": list(length)}
    return EpisodeSpec.model_validate(data)


def make_script(lines: list[str]) -> Script:
    return Script.model_validate({
        "episode_id": "en-A2-x00",
        "title_working": "Cheap coffee",
        "hook": "Where can you find cheap coffee?",
        "segments": [{
            "id": "s1",
            "type": "dialogue",
            "lines": [
                {"id": f"s1l{i}", "speaker": "anna", "text": text, "translation": {"vi": "..."}, "pause_after_ms": 1000}
                for i, text in enumerate(lines, start=1)
            ],
        }],
        "vocab": [{"word": "cheap", "gloss": {"en": "it does not cost a lot", "vi": "rẻ"}, "is_target": True}],
    })


def gates(report) -> set[str]:
    return {f.gate for f in report.gate_failures}


def test_clean_script_passes(pack, config):
    report = profile(make_script(CLEAN_LINES), make_spec(), config, pack)
    assert report.passed, format_report(report)
    assert report.in_level_ratio >= 0.95
    assert report.target_word_counts == {"cheap": 6}
    assert report.config_hash == config.config_hash


def test_one_b2_word_is_reported_with_its_line(pack, config):
    lines = CLEAN_LINES.copy()
    lines[1] = "Nevertheless, the coffee at the small shop is cheap."
    report = profile(make_script(lines), make_spec(), config, pack)
    assert [(t.lemma, t.line_id) for t in report.off_level_tokens] == [("nevertheless", "s1l2")]
    assert not report.passed
    assert "new_words" in gates(report)


def test_coverage_gate_fails_when_off_level_share_is_high(pack, config):
    lines = [line.replace("good", "magnificent").replace("small", "minuscule") for line in CLEAN_LINES]
    lines.append("Nevertheless, the cheap coffee is magnificent and economical.")
    report = profile(make_script(lines), make_spec(), config, pack)
    assert "coverage" in gates(report)
    failure = next(f for f in report.gate_failures if f.gate == "coverage")
    assert "magnificent" in failure.detail and "s1l7" in failure.line_ids


def test_too_few_target_repetitions(pack, config):
    lines = [line.replace("cheap", "good") for line in CLEAN_LINES[:3]] + CLEAN_LINES[3:]
    report = profile(make_script(lines), make_spec(), config, pack)
    assert report.target_word_counts == {"cheap": 3}
    assert "target_repetition" in gates(report)


def test_script_too_long_for_spec(pack, config):
    report = profile(make_script(CLEAN_LINES * 3), make_spec(length=(0.1, 0.3)), config, pack)
    assert "duration" in gates(report)
    assert report.estimated_duration_min > 0.3


def test_long_sentences_are_flagged(pack, config):
    lines = CLEAN_LINES + [
        "My friend and I always walk to the very old station near the big shop in the morning."
    ]
    report = profile(make_script(lines), make_spec(), config, pack)
    assert report.sentence_length.long_lines == ["s1l7"]


def test_short_sentences_pass_only_in_ceiling_mode(pack, config):
    lines = ["It is cheap.", "Yes, very cheap!", "Cheap tea, cheap coffee.", "I like cheap food."] * 2
    spec = make_spec(length=(0.05, 1.0))
    assert "sentence_length" in gates(profile(make_script(lines), spec, config, pack))
    ceiling = config.model_copy(update={"band": config.band.model_copy(update={"sentence_length_gate": "ceiling"})})
    assert "sentence_length" not in gates(profile(make_script(lines), spec, ceiling, pack))


def test_missing_vi_gloss_fails(pack, config):
    script = make_script(CLEAN_LINES)
    script.vocab[0].gloss.pop("vi")
    assert "vocab_gloss" in gates(profile(script, make_spec(), config, pack))


def test_phase_three_fixture_profiles(pack, config, script, spec):
    report = profile(script, spec, config, pack)
    text = format_report(report)
    assert "in-level ratio" in text and not report.passed
    assert {"target_repetition", "duration"} <= gates(report)


def test_curly_apostrophes_are_in_level(pack, config):
    straight = profile(make_script(CLEAN_LINES + ["I don't know. It's Anna's key, and it's cheap."]), make_spec(), config, pack)
    curly = profile(make_script(CLEAN_LINES + ["I don’t know. It’s Anna’s key, and it’s cheap."]), make_spec(), config, pack)
    assert curly.off_level_tokens == []
    assert curly.in_level_ratio == straight.in_level_ratio
    assert curly.sentence_length == straight.sentence_length


def test_inflected_target_forms_count(pack, config):
    spec = make_spec().model_copy(update={"target_words": ["rent"]})
    script = make_script(["I rent a small flat.", "Renting is not cheap.", "She rented a car.", "He rents a room."])
    script.vocab[0].word = "rent"
    report = profile(script, spec, config, pack)
    assert report.target_word_counts == {"rent": 4}


def test_multi_word_target_is_counted_as_a_phrase(pack, config):
    spec = make_spec().model_copy(update={"target_words": ["get up"]})
    report = profile(make_script(["I get up at six.", "Do you get up early?", "We got up late."]), spec, config, pack)
    assert report.target_word_counts == {"get up": 2}


def test_replay_mismatch_is_a_gate(pack, config, script, spec):
    data = script.model_dump()
    data["segments"].insert(1, {"id": "s9", "type": "replay", "lines": [
        {**data["segments"][0]["lines"][0], "id": "s9l1", "text": "Hello! Can I see the menu?"},
    ]})
    report = profile(Script.model_validate(data), spec, config, pack)
    failure = next(f for f in report.gate_failures if f.gate == "replay_mismatch")
    assert failure.line_ids == ["s9l1"]
