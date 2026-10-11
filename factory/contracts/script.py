from typing import Literal

from pydantic import Field, model_validator

from factory.contracts.base import Contract, Part

SegmentType = Literal["hook", "dialogue", "explanation", "replay", "quiz", "outro"]


class Line(Part):
    id: str
    speaker: str
    text: str
    # Keyed by support language. For an English target, `vi` is a translation; `en` is omitted.
    translation: dict[str, str] = {}
    pause_after_ms: int = Field(default=0, ge=0)
    visual_cue: str | None = None


class QuizItem(Part):
    id: str
    question: str
    options: list[str] = Field(min_length=2)
    answer_index: int = Field(ge=0)
    translation: dict[str, str] = {}

    @model_validator(mode="after")
    def _answer_in_range(self):
        if self.answer_index >= len(self.options):
            raise ValueError(f"quiz item {self.id}: answer_index out of range")
        return self


class Segment(Part):
    id: str
    type: SegmentType
    speed: Literal["slow", "natural"] | None = None
    layout: str | None = None
    lines: list[Line] = []
    items: list[QuizItem] = []


class VocabItem(Part):
    word: str
    # Keyed by support language. For an English target, `en` is a simple-English gloss.
    gloss: dict[str, str]
    is_target: bool


class Script(Contract):
    """An episode script, written by A2 and patched by A3 (architecture §4.3)."""

    schema_version: str = "1.0.0"
    episode_id: str
    title_working: str
    hook: str
    segments: list[Segment] = Field(min_length=1)
    vocab: list[VocabItem] = []
    grammar_notes: list[str] = []
    interaction_prompts: list[str] = []

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [s.id for s in self.segments]
        ids += [x.id for s in self.segments for x in [*s.lines, *s.items]]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate segment/line ids: {sorted(dupes)}")
        return self

    def iter_lines(self):
        for segment in self.segments:
            yield from segment.lines
