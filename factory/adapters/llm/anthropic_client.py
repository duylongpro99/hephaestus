"""Provider for the Anthropic Messages API (native SDK), one of the provider types in config/llm.yaml.

Uses structured outputs, the SDK Tool Runner, prompt caching on the stable system prefix and
server-side refusal fallback. With fallback, every billed attempt in `usage.iterations` is priced.
"""

from typing import Any

import anthropic
from anthropic import beta_tool, transform_schema
from pydantic import BaseModel, ValidationError

from factory.adapters.llm.base import LLMError, Price, StructuredResult, ToolSpec, cost_entry
from factory.contracts import CostEntry

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _tokens(usage: Any, name: str) -> int:
    return getattr(usage, name, 0) or 0


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


class AnthropicProvider:
    def __init__(
        self, *, name: str, model: str, client: anthropic.Anthropic, prices: dict[str, Price], params: dict,
        max_tokens: int, identity: str,
    ):
        self.name, self.model, self.client, self.prices = name, model, client, prices
        self.params, self.max_tokens, self.identity = params, max_tokens, identity

    def cost_entries(self, station: str, message: Any) -> list[CostEntry]:
        usage = message.usage
        iterations = getattr(usage, "iterations", None) or []
        attempts = [(getattr(it, "model", None) or message.model, it) for it in iterations] or [(message.model, usage)]
        return [
            cost_entry(
                station, self.name, model, self.prices.get(model),
                input_tokens=_tokens(a, "input_tokens"), output_tokens=_tokens(a, "output_tokens"),
                cache_read=_tokens(a, "cache_read_input_tokens"), cache_write=_tokens(a, "cache_creation_input_tokens"),
            )
            for model, a in attempts
        ]

    def _system(self, system: list[str]) -> list[dict]:
        blocks = [{"type": "text", "text": text} for text in system]
        if blocks:
            blocks[-1]["cache_control"] = {"type": "ephemeral"}
        return blocks

    def _common(self) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }

    def structured(
        self, *, station: str, system: list[str], user: str, output_model: type[BaseModel],
    ) -> StructuredResult:
        try:
            with self.client.beta.messages.stream(
                **self._common(),
                system=self._system(system),
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.params.get("effort", "high"),
                    "format": {"type": "json_schema", "schema": transform_schema(output_model)},
                },
            ) as stream:
                message = stream.get_final_message()
        except anthropic.APIError as exc:
            raise LLMError(f"{self.name}/{self.model}: {exc}") from exc
        costs = self.cost_entries(station, message)
        check_stop(message, costs)
        try:
            parsed = output_model.model_validate_json(final_text(message))
        except ValidationError as exc:
            raise LLMError(f"{station}: output did not match {output_model.__name__}: {exc}", costs) from exc
        return StructuredResult(parsed=parsed, costs=costs, raw=message)

    def tool_loop(
        self, *, station: str, system: list[str], user: str, tools: list[ToolSpec], max_iterations: int = 15,
    ) -> list[CostEntry]:
        runner = self.client.beta.messages.tool_runner(
            **self._common(),
            system=self._system(system),
            messages=[{"role": "user", "content": user}],
            tools=[_runner_tool(t) for t in tools],
            max_iterations=max_iterations,
            output_config={"effort": self.params.get("effort", "medium")},
        )
        costs: list[CostEntry] = []
        last = None
        try:
            for message in runner:
                costs += self.cost_entries(station, message)
                last = message
        except anthropic.APIError as exc:
            raise LLMError(f"{station}: {exc}", costs) from exc
        if last is not None:
            check_stop(last, costs)
        return costs


def _runner_tool(spec: ToolSpec):
    def handler(**arguments) -> str:
        return spec.call(arguments)

    return beta_tool(handler, name=spec.name, description=spec.description, input_schema=spec.schema())
