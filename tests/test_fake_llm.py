"""The fake LLM provider: replays fixtures, validated like a real provider's output."""

import json

import pytest
from pydantic import BaseModel

from factory.adapters.llm.base import LLMError, LLMProvider
from factory.adapters.llm.fake import FakeLLMProvider
from factory.agents.review_panel.agent import PanelVerdict
from tests.conftest import FIXTURES

XX_FIXTURES = FIXTURES / "xx-fixture" / "xx-A2-e2e"


def test_fake_llm_validates_its_fixture():
    llm: LLMProvider = FakeLLMProvider(XX_FIXTURES)
    result = llm.structured(station="review_examiner", system=[], user="", output_model=PanelVerdict)
    assert result.parsed.decision == "approve"
    assert [(c.vendor, c.usd, c.priced) for c in result.costs] == [("fake", 0.0, True)]

    class Other(BaseModel):
        something_else: int

    with pytest.raises(LLMError, match="does not match"):
        llm.structured(station="review_examiner", system=[], user="", output_model=Other)
    with pytest.raises(LLMError, match="no fixture"):
        llm.structured(station="nobody", system=[], user="", output_model=Other)


def test_fake_llm_identity_tracks_fixture_contents(tmp_path):
    (tmp_path / "s.json").write_text("{}")
    before = FakeLLMProvider(tmp_path).identity
    (tmp_path / "s.json").write_text('{"a": 1}')
    assert FakeLLMProvider(tmp_path).identity != before


def test_fake_llm_replays_tool_calls(tmp_path):
    from factory.adapters.llm.base import ToolSpec

    class Args(BaseModel):
        word: str

    seen = []
    tool = ToolSpec("note", "remember a word", Args, lambda a: seen.append(a.word) or "ok")
    (tmp_path / "editor.json").write_text(json.dumps([{"name": "note", "arguments": {"word": "kosa"}}]))
    FakeLLMProvider(tmp_path).tool_loop(station="editor", system=[], user="", tools=[tool])
    assert seen == ["kosa"]
