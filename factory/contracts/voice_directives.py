from typing import Literal

from factory.contracts.base import Contract, Part


class LineDirective(Part):
    line_id: str
    speaker: str
    voice: str  # a voice key of the pack; config/media.yaml maps it to a provider voice
    style_tags: list[str] = []
    rate: float  # in the pack's rate unit
    rate_unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    pause_ms: int  # silence after the line
    accent_overrides: dict[str, str] = {}  # word -> pronunciation
    variant: Literal["slow", "natural"]


class VoiceDirectives(Contract):
    """How each line is spoken (architecture §4.4), written by A6."""

    schema_version: str = "2.0.0"
    episode_id: str
    lines: list[LineDirective]
