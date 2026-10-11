from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from factory.contracts.base import Contract, Part


class RateTarget(Part):
    unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    min: float
    max: float


class EpisodeSpec(Contract):
    """The work order for one episode (architecture §4.2)."""

    schema_version: str = "1.0.0"
    episode_id: str
    channel: str
    level: str
    format: str
    theme: str
    target_words: list[str] = Field(min_length=1)
    review_words: list[str] = []
    grammar_point: str
    rate_target: RateTarget
    length_min: tuple[float, float]
    season_arc_beat: str | None = None
    cast: list[str] = Field(min_length=1)
    source: Literal["season", "adhoc"]
    season_id: str | None = None
    ordering: Literal["strict", "loose"] = "loose"
    publish_slot: datetime | None = None
    config_hash: str
    budget_usd: float

    @model_validator(mode="after")
    def _check(self):
        lo, hi = self.length_min
        if lo <= 0 or lo > hi:
            raise ValueError(f"length_min must be (min, max) with 0 < min <= max, got {self.length_min}")
        if self.rate_target.min > self.rate_target.max:
            raise ValueError("rate_target.min must not exceed rate_target.max")
        if self.source == "season" and not self.season_id:
            raise ValueError("a season spec needs season_id")
        return self
