"""The `en` Language Pack: spaCy tokens, an NGSL-derived CEFR lexicon and Open English WordNet."""

import json
import re
from functools import cached_property
from pathlib import Path

import yaml

from factory.tools.language_pack import (
    CEFR_LEVELS,
    DataLicense,
    Hint,
    Level,
    Ruby,
    Token,
    VoiceRef,
    at_or_below,
)

PACK_DIR = Path(__file__).resolve().parent
LEXICON_PATH = PACK_DIR / "data" / "lexicon.jsonl"
LICENSES_PATH = PACK_DIR / "licenses.yaml"
WN_DATA_DIR = PACK_DIR / "data" / "raw" / "wn"
WORDNET_LEXICON = "oewn:2025"

# Tokens that are in-level at every level: they carry no vocabulary load.
ALWAYS_IN_LEVEL_POS = {"PUNCT", "SYM", "SPACE", "NUM", "PROPN", "X"}
SPOKEN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)*")


class EnPack:
    code = "en"
    script_direction = "ltr"
    rate_unit = "wpm"
    native_rate = 150.0  # conversational American English, research.md §2.1
    fonts: list[str] = []
    voices: list[VoiceRef] = []

    @cached_property
    def nlp(self):
        import spacy

        return spacy.load("en_core_web_sm")

    @cached_property
    def _lexicon(self) -> tuple[dict[str, dict], dict[str, str]]:
        if not LEXICON_PATH.exists():
            raise FileNotFoundError(f"{LEXICON_PATH} is missing; run `uv run python -m packs.en.ingest`")
        headwords: dict[str, dict] = {}
        form_levels: dict[str, str] = {}
        for line in LEXICON_PATH.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            headwords[entry["headword"]] = entry
            if entry["level"] is None:
                continue
            for form in entry["forms"]:
                known = form_levels.get(form)
                if known is None or CEFR_LEVELS.index(entry["level"]) < CEFR_LEVELS.index(known):
                    form_levels[form] = entry["level"]
        return headwords, form_levels

    @cached_property
    def _wordnet(self):
        import wn

        wn.config.data_directory = WN_DATA_DIR
        try:
            return wn.Wordnet(WORDNET_LEXICON)
        except wn.Error as exc:
            raise RuntimeError(f"Open English WordNet is not installed; run `uv run python -m packs.en.ingest` ({exc})")

    @cached_property
    def licenses(self) -> list[DataLicense]:
        register = yaml.safe_load(LICENSES_PATH.read_text(encoding="utf-8"))
        return [
            DataLicense(name=s["dataset"], url=s["url"], license=s["license"], attribution=s["attribution"])
            for s in register["sources"]
        ]

    def tokenize(self, text: str) -> list[Token]:
        # Typographic apostrophes would split "don’t" into an unknown "n’t"; spaCy expects ASCII.
        doc = self.nlp(text.replace("\u2019", "'").replace("\u2018", "'"))
        sentence_of = {}
        for index, sent in enumerate(doc.sents):
            for tok in sent:
                sentence_of[tok.i] = index
        return [
            Token(
                surface=tok.text,
                lemma=tok.lemma_.lower(),
                pos=tok.pos_,
                sentence=sentence_of[tok.i],
                is_punct=tok.is_punct or tok.pos_ in {"PUNCT", "SYM", "SPACE"},
                is_num=tok.like_num or tok.pos_ == "NUM",
                is_proper=tok.pos_ == "PROPN",
            )
            for tok in doc
            if not tok.is_space
        ]

    def is_content(self, token: Token) -> bool:
        """Whether a token carries vocabulary load and counts towards coverage."""
        return not (token.is_punct or token.is_num or token.is_proper or token.pos in ALWAYS_IN_LEVEL_POS)

    def lemma_level(self, token: Token, framework: str = "cefr") -> Level | None:
        if framework != "cefr":
            raise ValueError(f"the en pack levels words on cefr only, not {framework}")
        if not self.is_content(token) or token.lemma.startswith("'"):
            return "PreA1"  # punctuation, numerals, proper nouns and clitics such as possessive 's
        return self.word_level(token.lemma) or self.word_level(token.surface.lower())

    def word_level(self, word: str) -> Level | None:
        headwords, form_levels = self._lexicon
        entry = headwords.get(word)
        if entry and entry["level"]:
            return entry["level"]
        return form_levels.get(word)

    def speech_units(self, text: str) -> int:
        # Spoken words: a contraction such as "don't" is one word, though spaCy splits it in two.
        return len(SPOKEN_WORD.findall(text))

    def reading_aids(self, text: str, policy: str) -> list[Ruby]:
        return []  # English has no reading aids

    def romanize(self, text: str) -> str | None:
        return None  # already Latin script

    def pronunciation_hints(self, text: str) -> list[Hint]:
        return []  # stress hints arrive with the Voice Director

    def dictionary_gloss(self, lemma: str, support_lang: str) -> str | None:
        if support_lang != "en":
            return None  # WordNet is monolingual; other glosses come from the Scriptwriter
        for synset in self._wordnet.synsets(lemma):
            definition = synset.definition()
            if definition:
                return definition
        return None

    def simpler_synonyms(self, lemma: str, level: str) -> list[str]:
        """WordNet synonyms of `lemma` at or below `level`, most frequent first."""
        headwords, _ = self._lexicon
        found: dict[str, None] = {}
        for synset in self._wordnet.synsets(lemma):
            for candidate in synset.lemmas():
                word = candidate.lower()
                if word != lemma and " " not in word and at_or_below(self.word_level(word), level):
                    found[word] = None

        def rank(word: str) -> int:
            entry = headwords.get(word) or {}
            return min(r for r in (entry.get("rank"), entry.get("spoken_rank"), 10_000) if r is not None)

        return sorted(found, key=rank)

    def lemma_forms(self, lemma: str) -> list[str]:
        """Inflected forms of a headword from the lexicon (empty when the word is not listed)."""
        headwords, _ = self._lexicon
        return list((headwords.get(lemma.lower()) or {}).get("forms", []))

    def level_wordlist(self, level: str) -> dict[str, list[str]]:
        """Headwords at or below `level`, grouped by level and sorted alphabetically."""
        headwords, _ = self._lexicon
        grouped: dict[str, list[str]] = {}
        for word, entry in sorted(headwords.items()):
            if at_or_below(entry["level"], level):
                grouped.setdefault(entry["level"], []).append(word)
        return {lv: grouped[lv] for lv in CEFR_LEVELS if lv in grouped}


Pack = EnPack
