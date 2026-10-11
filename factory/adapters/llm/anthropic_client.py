"""Thin wrapper over the Anthropic SDK: structured calls and tool loops, each priced into CostEntries.

The API key is read by the SDK from ANTHROPIC_API_KEY (or an `ant auth login` profile); it is
never passed in code or written to disk.
"""

from dataclasses import dataclass, field
from typing import Any

import anthropic
from anthropic import transform_schema
from pydantic import BaseModel, ValidationError

from factory.contracts import CostEntry

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens: input, output, cache write (5-minute TTL), cache read.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
}


class LLMError(RuntimeError):
    """A failed call. `costs` holds what was billed before the failure, so ledgers stay complete."""

    def __init__(self, message: str, costs: list[CostEntry] | None = None):
        super().__init__(message)
        self.costs = costs or []


def _tokens(usage: Any, name: str) -> int:
    return getattr(usage, name, 0) or 0


def price_usage(model: str, usage: Any) -> float | None:
    """USD for one attempt, or None when the model has no known price."""
    if model not in PRICES:
        return None
    p_in, p_out, p_write, p_read = PRICES[model]
    total = (
        _tokens(usage, "input_tokens") * p_in
        + _tokens(usage, "output_tokens") * p_out
        + _tokens(usage, "cache_creation_input_tokens") * p_write
        + _tokens(usage, "cache_read_input_tokens") * p_read
    )
    return round(total / 1_000_000, 6)


def cost_entries(station: str, message: Any) -> list[CostEntry]:
    """One entry per billed attempt.

    With server-side fallback, the top-level usage covers only the attempt that produced the
    message; `usage.iterations` lists every billed attempt with its own model.
    """
    usage = message.usage
    iterations = getattr(usage, "iterations", None) or []
    attempts = [(getattr(it, "model", None) or message.model, it) for it in iterations] or [(message.model, usage)]
    entries = []
    for model, attempt in attempts:
        usd = price_usage(model, attempt)
        entries.append(CostEntry(
            station=station,
            model=model,
            input_tokens=_tokens(attempt, "input_tokens"),
            output_tokens=_tokens(attempt, "output_tokens"),
            cache_creation_input_tokens=_tokens(attempt, "cache_creation_input_tokens"),
            cache_read_input_tokens=_tokens(attempt, "cache_read_input_tokens"),
            usd=usd or 0.0,
            priced=usd is not None,
        ))
    return entries


def check_stop(message: Any, costs: list[CostEntry]) -> None:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise LLMError(f"model refused the request (category: {category})", costs)
    if message.stop_reason == "max_tokens":
        raise LLMError("response hit max_tokens before finishing; raise max_tokens", costs)


def final_text(message: Any) -> str:
    """Text written after the last fallback switch (earlier blocks belong to a declined attempt)."""
    blocks = list(message.content)
    last_switch = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=-1)
    return "".join(b.text for b in blocks[last_switch + 1:] if b.type == "text")


@dataclass
class StructuredResult:
    parsed: BaseModel
    costs: list[CostEntry]
    message: Any = field(repr=False)


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, client: anthropic.Anthropic | None = None):
        self.model = model
        self.client = client or anthropic.Anthropic()

    def structured(
        self,
        *,
        station: str,
        system: list[dict],
        user: str,
        output_model: type[BaseModel],
        effort: str = "high",
        max_tokens: int = 64_000,
    ) -> StructuredResult:
        """One streamed call constrained to `output_model`'s JSON Schema, validated after the stop check."""
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": transform_schema(output_model)},
            },
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
        costs = cost_entries(station, message)
        check_stop(message, costs)
        try:
            parsed = output_model.model_validate_json(final_text(message))
        except ValidationError as exc:
            raise LLMError(f"{station}: output did not match {output_model.__name__}: {exc}", costs) from exc
        return StructuredResult(parsed=parsed, costs=costs, message=message)

    def tool_loop(
        self,
        *,
        station: str,
        system: list[dict],
        user: str,
        tools: list,
        effort: str = "medium",
        max_tokens: int = 16_000,
        max_iterations: int = 15,
    ) -> list[CostEntry]:
        """Run the SDK Tool Runner until the model stops calling tools; price every call."""
        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=tools,
            max_iterations=max_iterations,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        costs: list[CostEntry] = []
        last = None
        try:
            for message in runner:
                costs += cost_entries(station, message)
                last = message
        except anthropic.APIError as exc:
            raise LLMError(f"{station}: {exc}", costs) from exc
        if last is not None:
            check_stop(last, costs)
        return costs
