"""The Language Pack interface (architecture §4.0).

Stations and tools talk to a target language only through this interface, so a new
language is a new pack, not new station code.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from factory.config import pack_module

CEFR_LEVELS = ("PreA1", "A1", "A2", "B1", "B2", "C1", "C2")

Level = Literal["PreA1", "A1", "A2", "B1", "B2", "C1", "C2"]


def level_rank(level: str) -> int:
    return CEFR_LEVELS.index(level)


def at_or_below(level: str | None, ceiling: str) -> bool:
    return level is not None and level_rank(level) <= level_rank(ceiling)


@dataclass(frozen=True)
class Token:
    surface: str
    lemma: str
    pos: str  # Universal Dependencies POS tag
    sentence: int  # index of the sentence within the analysed text
    is_punct: bool = False
    is_num: bool = False
    is_proper: bool = False


@dataclass(frozen=True)
class Ruby:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Hint:
    start: int
    end: int
    kind: str
    value: str


@dataclass(frozen=True)
class VoiceRef:
    vendor: str
    id: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataLicense:
    name: str
    url: str
    license: str
    attribution: str


@runtime_checkable
class LanguagePack(Protocol):
    code: str
    script_direction: Literal["ltr", "rtl"]
    rate_unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    native_rate: float
    fonts: list[str]
    voices: list[VoiceRef]
    licenses: list[DataLicense]

    def tokenize(self, text: str) -> list[Token]: ...

    def lemma_level(self, token: Token, framework: str = "cefr") -> Level | None: ...

    def speech_units(self, text: str) -> int: ...

    def reading_aids(self, text: str, policy: str) -> list[Ruby]: ...

    def romanize(self, text: str) -> str | None: ...

    def pronunciation_hints(self, text: str) -> list[Hint]: ...

    def dictionary_gloss(self, lemma: str, support_lang: str) -> str | None: ...

    def dictionary_senses(self, lemma: str, support_lang: str, limit: int = 3) -> list[str]: ...

    def simpler_synonyms(self, lemma: str, level: str) -> list[str]: ...

    def lemma_forms(self, lemma: str) -> list[str]: ...

    def level_wordlist(self, level: str) -> dict[str, list[str]]: ...


def load_pack(code: str) -> LanguagePack:
    return pack_module(code).Pack()
