"""Fake LLM provider: canned outputs per station from fixture JSON. No network, zero cost.

`fixtures_dir/{station}.json` holds the station's output: for a structured call, the object
the model would return (validated against the requested model, so a contract change breaks the
fixture loudly); for a tool loop, a list of {"name", "arguments"} calls replayed in order.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from factory.adapters.llm.base import LLMError, StructuredResult, ToolSpec
from factory.contracts import CostEntry

VENDOR = "fake"


class FakeLLMProvider:
    def __init__(self, fixtures_dir: Path):
        self.fixtures_dir = fixtures_dir
        digest = hashlib.sha256()
        for path in sorted(fixtures_dir.glob("*.json")):
            digest.update(path.name.encode("utf-8") + path.read_bytes())
        self.identity = f"fake/fixtures#{digest.hexdigest()[:8]}"

    def _fixture(self, station: str):
        path = self.fixtures_dir / f"{station}.json"
        if not path.exists():
            raise LLMError(f"fake LLM: no fixture {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _cost(self, station: str) -> CostEntry:
        return CostEntry(station=station, vendor=VENDOR, model="fake", usd=0.0)

    def structured(
        self, *, station: str, system: list[str], user: str, output_model: type[BaseModel],
    ) -> StructuredResult:
        data = self._fixture(station)
        try:
            parsed = output_model.model_validate(data)
        except ValidationError as exc:
            raise LLMError(f"fake LLM: fixture for {station} does not match {output_model.__name__}: {exc}") from exc
        return StructuredResult(parsed=parsed, costs=[self._cost(station)], raw=data)

    def tool_loop(
        self, *, station: str, system: list[str], user: str, tools: list[ToolSpec], max_iterations: int = 15,
    ) -> list[CostEntry]:
        by_name = {tool.name: tool for tool in tools}
        for call in self._fixture(station)[:max_iterations]:
            if call["name"] not in by_name:
                raise LLMError(f"fake LLM: fixture for {station} calls unknown tool {call['name']}")
            by_name[call["name"]].call(call["arguments"])
        return [self._cost(station)]
