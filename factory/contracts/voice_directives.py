from typing import Literal

from factory.contracts.base import Contract, Part


class LineDirective(Part):
    line_id: str
    speaker: str
    vendor: str
    voice_id: str
    style_tags: list[str] = []
    rate: float  # in the pack's rate unit
    rate_unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    pause_ms: int  # silence after the line
    accent_overrides: dict[str, str] = {}  # word -> pronunciation
    variant: Literal["slow", "natural"]


class VoiceDirectives(Contract):
    """How each line is spoken (architecture §4.4), written by A6."""

    schema_version: str = "1.0.0"
    episode_id: str
    lines: list[LineDirective]
