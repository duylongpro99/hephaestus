"""Pack-agnostic conformance checks every Language Pack must pass (architecture §16).

A pack's conformance module star-imports these tests and defines two fixtures: `pack`, the
loaded pack, and `samples`, a `ConformanceSamples` with words and text from its language.
"""

from dataclasses import dataclass

from factory.tools.language_pack import LanguagePack, at_or_below, level_rank

ALLOWED_LICENSES = {"CC BY-SA 4.0", "CC BY 4.0"}
FORBIDDEN_DATASETS = ("evp", "english vocabulary profile", "oxford", "cefr-j")


@dataclass(frozen=True)
class ConformanceSamples:
    code: str
    rate_unit: str
    two_sentences: str  # text the tokenizer must split into exactly two sentences
    known_words: dict[str, str]  # word -> its level
    unknown_word: str  # a real-looking word missing from the leveled list
    spoken: tuple[str, int]  # text and its number of speech units
    synonym: tuple[str, str, str]  # (word, level, an in-level synonym the pack must offer)
    gloss_word: str  # a word with a dictionary entry in `gloss_language`
    gloss_language: str


def levels(pack, text):
    return [(t.lemma, pack.lemma_level(t)) for t in pack.tokenize(text) if not t.is_punct]


def test_implements_protocol(pack, samples):
    assert isinstance(pack, LanguagePack)
    assert pack.code == samples.code and pack.rate_unit == samples.rate_unit
    assert pack.script_direction in ("ltr", "rtl") and pack.native_rate > 0


def test_known_words_have_their_level(pack, samples):
    for word, level in samples.known_words.items():
        assert levels(pack, word) == [(word, level)], word


def test_unknown_word_has_no_level(pack, samples):
    [(_, level)] = levels(pack, samples.unknown_word)
    assert level is None


def test_numbers_and_punctuation_are_in_level(pack, samples):
    word = next(iter(samples.known_words))
    by_surface = {t.surface: pack.lemma_level(t) for t in pack.tokenize(f"{word} 25.")}
    assert by_surface["25"] == "PreA1" and by_surface["."] == "PreA1"


def test_sentences_are_indexed(pack, samples):
    assert {t.sentence for t in pack.tokenize(samples.two_sentences)} == {0, 1}


def test_speech_units(pack, samples):
    text, units = samples.spoken
    assert pack.speech_units(text) == units
    assert pack.speech_units("") == 0


def test_level_wordlist_is_cumulative(pack, samples):
    top = max(samples.known_words.values(), key=level_rank)
    grouped = pack.level_wordlist(top)
    assert grouped and all(at_or_below(level, top) for level in grouped)
    listed = {w for words in grouped.values() for w in words}
    assert {w for w, lv in samples.known_words.items() if at_or_below(lv, top)} <= listed
    assert all(words == sorted(words) for words in grouped.values())


def test_simpler_synonyms(pack, samples):
    word, level, expected = samples.synonym
    assert expected in pack.simpler_synonyms(word, level)


def test_dictionary_senses(pack, samples):
    senses = pack.dictionary_senses(samples.gloss_word, samples.gloss_language)
    assert 1 <= len(senses) <= 3 and all(isinstance(s, str) and s for s in senses)
    assert pack.dictionary_gloss(samples.gloss_word, samples.gloss_language) == senses[0]
    assert len(pack.dictionary_senses(samples.gloss_word, samples.gloss_language, limit=1)) == 1


def test_text_aids_return_lists(pack, samples):
    assert isinstance(pack.reading_aids(samples.two_sentences, "none"), list)
    assert isinstance(pack.pronunciation_hints(samples.two_sentences), list)


def test_licenses_are_clean(pack):
    assert all(lic.license in ALLOWED_LICENSES and lic.attribution for lic in pack.licenses)
    names = " ".join(lic.name for lic in pack.licenses).lower()
    assert not any(forbidden in names for forbidden in FORBIDDEN_DATASETS)
