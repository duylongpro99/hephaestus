"""The `xx-fixture` Language Pack: a tiny synthetic language for end-to-end runs (architecture §15).

Sixty made-up words split across A1 and A2, a whitespace-and-punctuation tokenizer and no
inflection, so a run needs no NLP models or downloaded data. The English glosses act as its
dictionary.
"""

import re

from factory.tools.language_pack import CEFR_LEVELS, DataLicense, Hint, Level, Ruby, Token, VoiceSpec, at_or_below

A1_WORDS = {
    "mi": "I", "tu": "you", "ka": "she", "lo": "he", "sa": "is", "na": "not", "ya": "yes", "ne": "no",
    "ta": "the", "e": "and", "pa": "want", "ko": "coffee", "te": "tea", "ba": "bread", "mo": "eat",
    "da": "drink", "ve": "see", "ri": "go", "ho": "home", "bu": "good", "ki": "what", "ze": "this",
    "la": "here", "fa": "friend", "ju": "today", "nu": "now", "so": "very", "wa": "water", "lu": "like",
    "do": "have",
}
A2_WORDS = {
    "mira": "menu", "kosa": "cheap", "peli": "pay", "valo": "choose", "tora": "order", "sena": "price",
    "buro": "expensive", "lika": "delicious", "mana": "morning", "sora": "small", "gela": "large",
    "dava": "give", "nori": "wait", "simo": "same", "kafu": "cafe", "polu": "pastry", "rina": "table",
    "sulo": "seat", "teka": "ticket", "vima": "window", "hana": "quickly", "lomi": "slowly",
    "piru": "probably", "zeta": "already", "kalu": "receipt", "moni": "money", "fera": "change",
    "ruto": "route", "nava": "near", "sefi": "tired",
}
WORDS: dict[str, tuple[Level, str]] = {
    **{w: ("A1", g) for w, g in A1_WORDS.items()}, **{w: ("A2", g) for w, g in A2_WORDS.items()},
}
SYNONYMS = {"lika": ["bu"]}  # delicious -> good
TOKEN = re.compile(r"\w+|[^\w\s]")
SENTENCE_END = {".", "!", "?"}


class XxFixturePack:
    code = "xx-fixture"
    script_direction = "ltr"
    rate_unit = "wpm"
    native_rate = 150.0
    fonts: list[str] = []
    voices: list[VoiceSpec] = [
        VoiceSpec(key="xx-a", locale="xx", gender="female"), VoiceSpec(key="xx-b", locale="xx", gender="male"),
    ]
    licenses: list[DataLicense] = []  # every word is invented for this pack

    def tokenize(self, text: str) -> list[Token]:
        tokens, sentence, start = [], 0, True
        for surface in TOKEN.findall(text):
            punct, num = not surface[0].isalnum(), surface.isdigit()
            proper = surface[0].isupper() and not start and surface.lower() not in WORDS
            pos = "PUNCT" if punct else "NUM" if num else "PROPN" if proper else "X"
            tokens.append(Token(surface=surface, lemma=surface.lower(), pos=pos, sentence=sentence,
                                is_punct=punct, is_num=num, is_proper=proper))
            start = surface in SENTENCE_END
            if start:
                sentence += 1
        return tokens

    def lemma_level(self, token: Token, framework: str = "cefr") -> Level | None:
        if framework != "cefr":
            raise ValueError(f"the xx-fixture pack levels words on cefr only, not {framework}")
        if token.is_punct or token.is_num or token.is_proper:
            return "PreA1"
        entry = WORDS.get(token.lemma)
        return entry[0] if entry else None

    def speech_units(self, text: str) -> int:
        return sum(1 for t in self.tokenize(text) if not t.is_punct)

    def reading_aids(self, text: str, policy: str) -> list[Ruby]:
        return []

    def romanize(self, text: str) -> str | None:
        return None

    def pronunciation_hints(self, text: str) -> list[Hint]:
        return []

    def dictionary_gloss(self, lemma: str, support_lang: str) -> str | None:
        senses = self.dictionary_senses(lemma, support_lang, limit=1)
        return senses[0] if senses else None

    def dictionary_senses(self, lemma: str, support_lang: str, limit: int = 3) -> list[str]:
        entry = WORDS.get(lemma.lower())
        return [entry[1]][:limit] if entry and support_lang == "en" else []

    def simpler_synonyms(self, lemma: str, level: str) -> list[str]:
        return [w for w in SYNONYMS.get(lemma.lower(), []) if at_or_below(WORDS[w][0], level)]

    def lemma_forms(self, lemma: str) -> list[str]:
        return [lemma.lower()] if lemma.lower() in WORDS else []

    def level_wordlist(self, level: str) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for word, (word_level, _) in sorted(WORDS.items()):
            if at_or_below(word_level, level):
                grouped.setdefault(word_level, []).append(word)
        return {lv: grouped[lv] for lv in CEFR_LEVELS if lv in grouped}


Pack = XxFixturePack
