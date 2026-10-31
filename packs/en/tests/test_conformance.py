"""Conformance suite for the en Language Pack (architecture §16): the shared checks plus en's own."""

import pytest
import yaml

from factory.tools.language_pack import at_or_below, load_pack
from packs.en.ingest import LICENSES_PATH
from tests.pack_conformance import *  # noqa: F403
from tests.pack_conformance import ConformanceSamples, levels


@pytest.fixture(scope="module")
def pack():
    return load_pack("en")


@pytest.fixture(scope="module")
def samples():
    return ConformanceSamples(
        code="en", rate_unit="wpm", two_sentences="I like tea. She likes coffee.",
        known_words={"go": "A1", "rent": "A2"}, unknown_word="photosynthesis", spoken=("I don't like it.", 4),
        synonym=("purchase", "A2", "buy"), gloss_word="headache", gloss_language="en",
    )


def test_irregular_past_resolves_to_lemma(pack):
    assert levels(pack, "went") == [("go", "A1")]


def test_progressive_resolves_to_lemma(pack):
    assert [lemma for lemma, _ in levels(pack, "running")] == ["run"]


def test_word_ranked_above_1000_is_above_a2(pack):
    [(lemma, level)] = levels(pack, "nevertheless")
    assert lemma == "nevertheless"
    assert not at_or_below(level, "A2")


def test_contraction_is_two_in_level_tokens(pack):
    result = levels(pack, "don't")
    assert len(result) == 2
    assert all(at_or_below(level, "A2") for _, level in result)


def test_names_are_in_level(pack):
    tokens = pack.tokenize("Anna paid 25 dollars.")
    assert {t.surface: pack.lemma_level(t) for t in tokens}["Anna"] == "PreA1"


def test_supplement_covers_everyday_words(pack):
    assert at_or_below(pack.word_level("breakfast"), "A1")
    assert at_or_below(pack.word_level("hungry"), "A2")


def test_dictionary_gloss(pack):
    assert pack.dictionary_gloss("purchase", "en")
    assert pack.dictionary_gloss("purchase", "vi") is None


def test_dictionary_senses_list_more_than_the_first(pack):
    senses = pack.dictionary_senses("headache", "en")
    assert 1 < len(senses) <= 3 and any("pain" in s for s in senses)
    assert pack.dictionary_senses("headache", "vi") == []


def test_license_register_matches_the_pack(pack):
    register = yaml.safe_load(LICENSES_PATH.read_text(encoding="utf-8"))
    assert all(len(s["sha256"]) == 64 for s in register["sources"])
    assert len(pack.licenses) == len(register["sources"])
