"""Provider layer tests with fake SDK clients. No network."""

import json
from types import SimpleNamespace as NS

import pytest
from pydantic import BaseModel

from factory.adapters.llm.anthropic_client import AnthropicProvider, final_text
from factory.adapters.llm.base import LLMError, Price, ToolSpec
from factory.adapters.llm.openai_compatible import OpenAICompatibleProvider, usage_tokens
from factory.adapters.llm.router import load_llm_config, provider_for


class Answer(BaseModel):
    word: str
    count: int


def completion(content=None, tool_calls=None, finish="stop", usage=None, reasoning=None):
    message = NS(content=content, tool_calls=tool_calls, role="assistant")
    if reasoning:
        message.reasoning_content = reasoning
    message.model_dump = lambda exclude_none=True: {
        k: v for k, v in vars(message).items() if k != "model_dump" and v is not None and k != "tool_calls"
    } | ({"tool_calls": [{"id": c.id, "type": "function", "function": {"name": c.function.name,
                                                                         "arguments": c.function.arguments}}
                          for c in tool_calls]} if tool_calls else {})
    return NS(choices=[NS(message=message, finish_reason=finish)], model="deepseek-v4-pro",
              usage=usage or NS(prompt_tokens=1000, completion_tokens=100, prompt_cache_hit_tokens=800))


class FakeOpenAI:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        return self.responses.pop(0)


def openai_provider(client, **kw):
    return OpenAICompatibleProvider(
        name="deepseek", model="deepseek-v4-pro", client=client, price=Price(input=1.0, cached_input=0.1, output=2.0),
        params={"reasoning_effort": "high"}, max_tokens=1000, identity="deepseek/deepseek-v4-pro#x", **kw,
    )


def test_structured_uses_json_mode_and_prices_cache_hits():
    client = FakeOpenAI([completion('{"word": "rent", "count": 5}')])
    result = openai_provider(client).structured(station="a2", system=["rules"], user="go", output_model=Answer)
    assert result.parsed == Answer(word="rent", count=5)
    request = client.requests[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["reasoning_effort"] == "high"
    assert "JSON Schema" in request["messages"][0]["content"]
    [cost] = result.costs
    assert (cost.input_tokens, cost.cache_read_input_tokens, cost.output_tokens) == (200, 800, 100)
    assert cost.usd == pytest.approx((200 * 1.0 + 800 * 0.1 + 100 * 2.0) / 1e6)


def test_invalid_json_is_repaired_once():
    client = FakeOpenAI([completion('{"word": "rent"}'), completion('{"word": "rent", "count": 5}')])
    result = openai_provider(client).structured(station="a2", system=["rules"], user="go", output_model=Answer)
    assert result.parsed.count == 5 and len(result.costs) == 2
    assert "did not validate" in client.requests[1]["messages"][-1]["content"]


def test_unrepairable_json_raises_with_costs():
    client = FakeOpenAI([completion("not json"), completion("still not json")])
    with pytest.raises(LLMError) as err:
        openai_provider(client).structured(station="a2", system=["r"], user="go", output_model=Answer)
    assert len(err.value.costs) == 2


def test_truncated_output_raises():
    client = FakeOpenAI([completion('{"word": "re', finish="length")])
    with pytest.raises(LLMError, match="max_tokens"):
        openai_provider(client).structured(station="a2", system=["r"], user="go", output_model=Answer)


class Echo(BaseModel):
    text: str


def test_tool_loop_runs_tools_and_keeps_reasoning_content():
    call = NS(id="c1", function=NS(name="echo", arguments='{"text": "hi"}'))
    client = FakeOpenAI([
        completion(tool_calls=[call], finish="tool_calls", reasoning="I should echo."),
        completion("done", reasoning="Finished."),
    ])
    seen = []
    tool = ToolSpec("echo", "Echo text.", Echo, lambda a: seen.append(a.text) or f"echoed {a.text}")
    costs = openai_provider(client).tool_loop(station="a3", system=["r"], user="go", tools=[tool])
    assert seen == ["hi"] and len(costs) == 2
    second = client.requests[1]["messages"]
    assert second[2]["reasoning_content"] == "I should echo."  # DeepSeek requires it in tool loops
    assert second[3] == {"role": "tool", "tool_call_id": "c1", "content": "echoed hi"}
    assert client.requests[0]["tools"][0]["function"]["parameters"]["properties"]["text"]["type"] == "string"


def test_tool_errors_go_back_to_the_model():
    tool = ToolSpec("echo", "Echo.", Echo, lambda a: (_ for _ in ()).throw(ValueError("bad line id")))
    assert tool.call({"text": "x"}) == "error: bad line id"
    assert tool.call({"wrong": 1}).startswith("error:")


def test_usage_shapes():
    assert usage_tokens(NS(prompt_tokens=10, completion_tokens=2, prompt_tokens_details=NS(cached_tokens=4))) == (6, 2, 4)
    assert usage_tokens(NS(prompt_tokens=10, completion_tokens=2, prompt_cache_hit_tokens=7)) == (3, 2, 7)


def test_llm_config_routes_every_spike_role():
    config = load_llm_config()
    for role in ("a2_scriptwriter", "a3_level_editor", "review_examiner", "review_learner"):
        assert config.role(role).provider in config.providers
    assert config.role("a2_scriptwriter").identity() != config.role("review_examiner").identity()


def test_missing_api_key_names_the_env_var(monkeypatch):
    config = load_llm_config()
    env = config.providers[config.role("a2_scriptwriter").provider].api_key_env
    monkeypatch.delenv(env, raising=False)
    with pytest.raises(LLMError, match=env):
        provider_for("a2_scriptwriter", config)


def test_router_builds_openai_compatible_provider_with_injected_client():
    provider = provider_for("a2_scriptwriter", client=FakeOpenAI([]))
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.identity.startswith("deepseek/deepseek-v4-pro#")


class _Attempt(NS):
    pass


def test_anthropic_fallback_attempts_are_each_priced():
    prices = {"claude-opus-5-5": Price(input=4.0, output=20.0), "claude-opus-4-8": Price(input=5.0, output=25.0)}
    provider = AnthropicProvider(name="anthropic", model="claude-opus-5-5", client=None, prices=prices, params={},
                                 max_tokens=1000, identity="anthropic/claude-opus-5-5#x")
    usage = _Attempt(input_tokens=1, output_tokens=1, iterations=[
        _Attempt(model="claude-opus-5-5", input_tokens=1_000_000, output_tokens=0),
        _Attempt(model="claude-opus-4-8", input_tokens=1_000_000, output_tokens=0),
        _Attempt(model="claude-mystery", input_tokens=10, output_tokens=0),
    ])
    entries = provider.cost_entries("a2", NS(model="claude-opus-4-8", usage=usage))
    assert [e.usd for e in entries] == [4.0, 5.0, 0.0]
    assert [e.priced for e in entries] == [True, True, False]


def test_anthropic_final_text_skips_the_declined_attempt():
    blocks = [NS(type="text", text='{"partial'), NS(type="fallback"), NS(type="text", text='{"ok": 1}')]
    assert final_text(NS(content=blocks)) == '{"ok": 1}'
