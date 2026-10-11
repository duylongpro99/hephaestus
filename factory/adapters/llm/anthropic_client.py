"""Thin wrapper over the Anthropic SDK: structured calls and tool loops, each priced into a CostEntry.

The API key is read by the SDK from ANTHROPIC_API_KEY (or an `ant auth login` profile); it is
never passed in code or written to disk.
"""

from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import BaseModel

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
    pass


def price_usage(model: str, usage: Any) -> float:
    if model not in PRICES:
        raise LLMError(f"no price for model {model}; add it to PRICES")
    p_in, p_out, p_write, p_read = PRICES[model]
    tokens = (
        (usage.input_tokens or 0) * p_in
        + (usage.output_tokens or 0) * p_out
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p_write
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p_read
    )
    return round(tokens / 1_000_000, 6)


def cost_entry(station: str, message: Any) -> CostEntry:
    usage = message.usage
    return CostEntry(
        station=station,
        model=message.model,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        usd=price_usage(message.model, usage),
    )


def check_stop(message: Any) -> None:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise LLMError(f"model refused the request (category: {category})")
    if message.stop_reason == "max_tokens":
        raise LLMError("response hit max_tokens before finishing; raise max_tokens")


@dataclass
class StructuredResult:
    parsed: BaseModel
    cost: CostEntry
    message: Any


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
        """One streamed call whose final text is validated against `output_model`."""
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_model,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
        check_stop(message)
        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            text = next((b.text for b in message.content if b.type == "text"), "")
            parsed = output_model.model_validate_json(text)
        return StructuredResult(parsed=parsed, cost=cost_entry(station, message), message=message)

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
    ) -> tuple[list[CostEntry], Any]:
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
        costs, last = [], None
        for message in runner:
            costs.append(cost_entry(station, message))
            last = message
        if last is not None:
            check_stop(last)
        return costs, last
