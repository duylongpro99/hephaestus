"""Provider-neutral LLM interface. Each factory role gets a provider from `config/llm.yaml`.

Stations depend only on `LLMProvider`: a structured call that returns a validated pydantic
model, and a tool loop over `ToolSpec`s. Every billed call becomes CostEntries.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from factory.contracts import CostEntry


class LLMError(RuntimeError):
    """A failed call. `costs` holds what was billed before the failure, so ledgers stay complete."""

    def __init__(self, message: str, costs: list[CostEntry] | None = None):
        super().__init__(message)
        self.costs = costs or []


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    output: float
    cached_input: float | None = None  # cache-read price; defaults to the input price
    cache_write: float | None = None  # cache-write price; defaults to the input price

    def usd(self, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
        total = (
            input_tokens * self.input
            + output_tokens * self.output
            + cache_read * (self.cached_input if self.cached_input is not None else self.input)
            + cache_write * (self.cache_write if self.cache_write is not None else self.input)
        )
        return round(total / 1_000_000, 6)


def cost_entry(
    station: str, vendor: str, model: str, price: Price | None, *,
    input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0,
) -> CostEntry:
    """`input_tokens` excludes cached tokens; an unknown price is recorded, never raised."""
    usd = price.usd(input_tokens, output_tokens, cache_read, cache_write) if price else None
    return CostEntry(
        station=station, vendor=vendor, model=model,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cache_creation_input_tokens=cache_write, cache_read_input_tokens=cache_read,
        usd=usd or 0.0, priced=usd is not None,
    )


@dataclass
class ToolSpec:
    """A tool any provider can expose: a JSON Schema from `input_model` and a Python handler."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], str]

    def schema(self) -> dict:
        return self.input_model.model_json_schema()

    def call(self, arguments: dict) -> str:
        try:
            return self.handler(self.input_model.model_validate(arguments))
        except ValueError as exc:  # includes pydantic ValidationError and the stations' edit errors
            return f"error: {exc}"


@dataclass
class StructuredResult:
    parsed: BaseModel
    costs: list[CostEntry]
    raw: Any = field(default=None, repr=False)


class LLMProvider(Protocol):
    """One configured model behind one vendor endpoint."""

    identity: str  # provider/model plus a hash of the role's request parameters

    def structured(
        self, *, station: str, system: list[str], user: str, output_model: type[BaseModel],
    ) -> StructuredResult: ...

    def tool_loop(
        self, *, station: str, system: list[str], user: str, tools: list[ToolSpec], max_iterations: int = 15,
    ) -> list[CostEntry]: ...
