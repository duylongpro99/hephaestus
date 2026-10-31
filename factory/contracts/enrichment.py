from factory.contracts.base import Contract, Part


class RubySpan(Part):
    start: int
    end: int
    text: str


class HintSpan(Part):
    start: int
    end: int
    kind: str
    value: str


class LineEnrichment(Part):
    line_id: str
    ruby: list[RubySpan] = []
    romanization: str | None = None
    hints: list[HintSpan] = []


class Enrichment(Contract):
    """Reading aids per line from the Language Pack (architecture §7, C2). Lines without aids are omitted."""

    schema_version: str = "1.0.0"
    episode_id: str
    policy: str
    lines: list[LineEnrichment] = []
