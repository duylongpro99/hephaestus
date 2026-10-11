from typing import Literal

from pydantic import computed_field

from factory.contracts.base import Contract, Part

GateName = Literal[
    "coverage", "new_words", "target_repetition", "sentence_length", "duration", "vocab_gloss"
]


class OffLevelToken(Part):
    line_id: str
    surface: str
    lemma: str
    level: str | None  # None means the lemma is not in the pack's leveled list


class SentenceLengthStats(Part):
    mean: float
    min: int
    max: int
    band: tuple[int, int]
    sentence_count: int
    long_lines: list[str]  # line ids holding a sentence longer than the band maximum
    long_share: float


class GateFailure(Part):
    gate: GateName
    detail: str
    line_ids: list[str] = []


class LevelReport(Contract):
    """Code-gate verdict on a script (architecture §4.4), written by the profiler."""

    schema_version: str = "1.0.0"
    episode_id: str
    level: str
    config_hash: str
    content_token_count: int
    in_level_ratio: float
    new_word_ratio: float
    off_level_tokens: list[OffLevelToken]
    target_word_counts: dict[str, int]
    sentence_length: SentenceLengthStats
    word_count: int
    estimated_duration_min: float
    gate_failures: list[GateFailure]

    @computed_field
    @property
    def passed(self) -> bool:
        return not self.gate_failures
