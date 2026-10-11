from datetime import datetime, timezone

from pydantic import Field, computed_field

from factory.contracts.base import Contract, Part


class CostEntry(Part):
    """One billed call."""

    station: str
    vendor: str = "anthropic"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    usd: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CostLedger(Contract):
    """Running cost of an episode against its budget (architecture §4.4)."""

    schema_version: str = "1.0.0"
    episode_id: str
    budget_usd: float
    entries: list[CostEntry] = []

    @computed_field
    @property
    def total_usd(self) -> float:
        return round(sum(entry.usd for entry in self.entries), 6)

    def station_usd(self, station: str) -> float:
        return round(sum(e.usd for e in self.entries if e.station == station), 6)
