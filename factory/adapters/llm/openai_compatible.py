"""Provider for any OpenAI-compatible chat/completions endpoint (DeepSeek, Qwen, OpenRouter, Ollama, ...).

Structured output uses `response_format: json_object` with the JSON Schema in the system prompt,
because vendors differ on `json_schema` support; the reply is validated in code and, if invalid,
sent back once for repair. Vendor-specific request fields (DeepSeek `thinking`, `reasoning_effort`)
come from the role's `params` in config/llm.yaml.
"""

import json
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from factory.adapters.llm.base import LLMError, Price, StructuredResult, ToolSpec, cost_entry
from factory.contracts import CostEntry

SCHEMA_INSTRUCTION = (
    "# Output format\n"
    "Reply with one JSON object only, no prose and no code fences. It must validate against this "
    "JSON Schema:\n{schema}"
)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    value = getattr(obj, name, None)
    if value is None and isinstance(obj, dict):
        value = obj.get(name)
    return default if value is None else value


def usage_tokens(usage: Any) -> tuple[int, int, int]:
    """(uncached input, output, cached input) across vendor usage shapes."""
    if usage is None:
        return 0, 0, 0
    prompt = _get(usage, "prompt_tokens", 0)
    output = _get(usage, "completion_tokens", 0)
    cached = _get(usage, "prompt_cache_hit_tokens")  # DeepSeek
    if cached is None:
        cached = _get(_get(usage, "prompt_tokens_details"), "cached_tokens", 0)  # OpenAI, Qwen
    return max(prompt - cached, 0), output, cached


def assistant_message(message: Any) -> dict:
    """The assistant turn to send back, keeping vendor fields such as DeepSeek's reasoning_content."""
    data = message.model_dump(exclude_none=True) if hasattr(message, "model_dump") else dict(message)
    data["role"] = "assistant"
    return data


class OpenAICompatibleProvider:
    def __init__(
        self, *, name: str, model: str, client: Any, price: Price | None, params: dict, max_tokens: int,
        identity: str, repair_attempts: int = 1,
    ):
        self.name, self.model, self.client, self.price = name, model, client, price
        self.params, self.max_tokens, self.identity = params, max_tokens, identity
        self.repair_attempts = repair_attempts

    def _cost(self, station: str, response: Any) -> CostEntry:
        uncached, output, cached = usage_tokens(_get(response, "usage"))
        return cost_entry(station, self.name, _get(response, "model", self.model), self.price,
                          input_tokens=uncached, output_tokens=output, cache_read=cached)

    def _create(self, costs: list[CostEntry], messages: list[dict], **extra) -> Any:
        try:
            return self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=self.max_tokens, **self.params, **extra,
            )
        except openai.APIError as exc:
            raise LLMError(f"{self.name}/{self.model}: {exc}", costs) from exc

    def structured(
        self, *, station: str, system: list[str], user: str, output_model: type[BaseModel],
    ) -> StructuredResult:
        schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False, sort_keys=True)
        messages = [
            {"role": "system", "content": "\n\n".join([*system, SCHEMA_INSTRUCTION.format(schema=schema)])},
            {"role": "user", "content": user},
        ]
        costs: list[CostEntry] = []
        for attempt in range(self.repair_attempts + 1):
            response = self._create(costs, messages, response_format={"type": "json_object"})
            costs.append(self._cost(station, response))
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise LLMError(f"{station}: response hit max_tokens ({self.max_tokens}); raise it", costs)
            content = choice.message.content or ""
            try:
                return StructuredResult(parsed=output_model.model_validate_json(content), costs=costs, raw=response)
            except ValidationError as exc:
                error = exc
            messages += [
                assistant_message(choice.message),
                {"role": "user", "content": (
                    "That JSON did not validate against the schema:\n"
                    f"{error}\nReturn the complete corrected JSON object."
                )},
            ]
        raise LLMError(f"{station}: output did not match {output_model.__name__} after "
                       f"{self.repair_attempts} repair attempt(s): {error}", costs)

    def tool_loop(
        self, *, station: str, system: list[str], user: str, tools: list[ToolSpec], max_iterations: int = 15,
    ) -> list[CostEntry]:
        by_name = {tool.name: tool for tool in tools}
        tool_defs = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema()}}
            for t in tools
        ]
        messages: list[dict] = [{"role": "system", "content": "\n\n".join(system)}, {"role": "user", "content": user}]
        costs: list[CostEntry] = []
        for _ in range(max_iterations):
            response = self._create(costs, messages, tools=tool_defs)
            costs.append(self._cost(station, response))
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise LLMError(f"{station}: response hit max_tokens ({self.max_tokens})", costs)
            calls = choice.message.tool_calls or []
            messages.append(assistant_message(choice.message))
            if not calls:
                return costs
            for call in calls:
                tool = by_name.get(call.function.name)
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    result = f"error: arguments are not valid JSON: {exc}"
                else:
                    result = tool.call(arguments) if tool else f"error: unknown tool {call.function.name}"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return costs  # iteration budget spent; the caller re-profiles the script
