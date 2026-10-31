"""Conformance suite for the xx-fixture Language Pack (architecture §16)."""

import pytest

from factory.tools.language_pack import load_pack
from tests.pack_conformance import *  # noqa: F403
from tests.pack_conformance import ConformanceSamples


@pytest.fixture(scope="module")
def pack():
    return load_pack("xx-fixture")


@pytest.fixture(scope="module")
def samples():
    return ConformanceSamples(
        code="xx-fixture", rate_unit="wpm", two_sentences="Mi pa ko. Tu pa te?",
        known_words={"ko": "A1", "kosa": "A2"}, unknown_word="zorbix", spoken=("Ya, mi lu ko!", 4),
        synonym=("lika", "A1", "bu"), gloss_word="kosa", gloss_language="en",
    )


def test_wordlist_size(pack):
    grouped = pack.level_wordlist("A2")
    assert {lv: len(words) for lv, words in grouped.items()} == {"A1": 30, "A2": 30}


def test_capitalised_unknown_word_mid_sentence_is_a_name(pack):
    [_, name, _] = pack.tokenize("Tu Kira?")
    assert name.is_proper and pack.lemma_level(name) == "PreA1"
