"""Conformance suite for the en Language Pack (architecture §16)."""

import pytest
import yaml

from factory.tools.language_pack import LanguagePack, at_or_below, load_pack
from packs.en.ingest import LICENSES_PATH


@pytest.fixture(scope="module")
def pack():
    return load_pack("en")


def levels(pack, text):
    return [(t.lemma, pack.lemma_level(t)) for t in pack.tokenize(text) if not t.is_punct]


def test_implements_protocol(pack):
    assert isinstance(pack, LanguagePack)
    assert pack.code == "en" and pack.rate_unit == "wpm"


def test_irregular_past_resolves_to_lemma(pack):
    assert levels(pack, "went") == [("go", "A1")]


def test_progressive_resolves_to_lemma(pack):
    assert [lemma for lemma, _ in levels(pack, "running")] == ["run"]


def test_word_ranked_above_1000_is_above_a2(pack):
    [(lemma, level)] = levels(pack, "nevertheless")
    assert lemma == "nevertheless"
    assert not at_or_below(level, "A2")


def test_unknown_word_has_no_level(pack):
    [(_, level)] = levels(pack, "photosynthesis")
    assert level is None


def test_contraction_is_two_in_level_tokens(pack):
    result = levels(pack, "don't")
    assert len(result) == 2
    assert all(at_or_below(level, "A2") for _, level in result)


def test_contraction_is_one_spoken_word(pack):
    assert pack.speech_units("I don't like it.") == 4


def test_names_numbers_and_punctuation_are_in_level(pack):
    tokens = pack.tokenize("Anna paid 25 dollars.")
    by_surface = {t.surface: pack.lemma_level(t) for t in tokens}
    assert by_surface["Anna"] == "PreA1"
    assert by_surface["25"] == "PreA1"
    assert by_surface["."] == "PreA1"


def test_supplement_covers_everyday_words(pack):
    assert at_or_below(pack.word_level("breakfast"), "A1")
    assert at_or_below(pack.word_level("hungry"), "A2")


def test_simpler_synonyms(pack):
    assert "buy" in pack.simpler_synonyms("purchase", "A2")


def test_dictionary_gloss(pack):
    assert pack.dictionary_gloss("purchase", "en")
    assert pack.dictionary_gloss("purchase", "vi") is None


def test_dictionary_senses_list_more_than_the_first(pack):
    senses = pack.dictionary_senses("headache", "en")
    assert 1 < len(senses) <= 3 and any("pain" in s for s in senses)
    assert pack.dictionary_senses("headache", "vi") == []


def test_sentences_are_indexed(pack):
    tokens = pack.tokenize("I like tea. She likes coffee.")
    assert {t.sentence for t in tokens} == {0, 1}


def test_license_register_is_clean(pack):
    register = yaml.safe_load(LICENSES_PATH.read_text(encoding="utf-8"))
    allowed = {"CC BY-SA 4.0", "CC BY 4.0"}
    assert {s["license"] for s in register["sources"]} <= allowed
    assert all(len(s["sha256"]) == 64 and s["attribution"] for s in register["sources"])
    names = " ".join(s["dataset"] for s in register["sources"]).lower()
    for forbidden in ("evp", "english vocabulary profile", "oxford", "cefr-j"):
        assert forbidden not in names
    assert len(pack.licenses) == len(register["sources"])
