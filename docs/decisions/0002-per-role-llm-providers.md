# ADR 0002: Per-role LLM providers

- **Date:** 2026-10-11
- **Status:** accepted
- **Decided by:** the user (project owner)
- **Supersedes:** the single-vendor model policy in [architecture.md §3](../architecture.md), for how
  each role's model is chosen. The roles themselves and their inputs and outputs are unchanged.

## Decision

Each factory role (A2 Scriptwriter, A3 Level Editor, the review personas, and later roles) gets
its own LLM provider and model. Routing lives in [`config/llm.yaml`](../../config/llm.yaml):

- `providers`: each endpoint's type, its `base_url`, and the **name** of the environment
  variable holding its key. Keys are never written to a file.
- `prices`: USD per million tokens per provider and model. A model without a price still runs;
  its cost is recorded with `priced: false`.
- `roles`: for each role, the provider, model, `max_tokens` and request `params`.

There are two provider types:

| Type | Covers | Notes |
|---|---|---|
| `openai_compatible` | DeepSeek, Qwen (Model Studio), OpenRouter, Groq, Together, Ollama, vLLM, LM Studio, ... | Structured output uses `response_format: json_object` with the JSON Schema in the system prompt and validation in code, plus one repair round. Tool loops send every assistant message back as-is, which keeps DeepSeek's `reasoning_content`. |
| `anthropic` | Claude via the native SDK | Structured outputs, the Tool Runner, prompt caching and server-side refusal fallback. |

Stations depend only on `factory/adapters/llm/base.py` (`LLMProvider`, `ToolSpec`) and get their
provider from `factory/adapters/llm/router.py`. A role's provider, model and params are part of
its `station_version`, so changing the routing never reuses an old artifact.

## First routing (EN A2 spike)

| Role | Provider | Model | Why |
|---|---|---|---|
| a2_scriptwriter | DeepSeek | deepseek-v4-pro, thinking on | Strong writer at low cost |
| a3_level_editor | DeepSeek | deepseek-v4-pro, thinking on | Supports tool calls in thinking mode |
| review_examiner | Qwen | qwen3-max | A different vendor from the writer |
| review_learner | Qwen | qwen3-max | A different vendor from the writer |

Putting both reviewers on a different vendor from the writer addresses the main risk in
[ADR 0001](0001-first-slice-and-spike-scope.md) decision 3: the panel judging its own model
family's output. The two personas still share one model, as they did before.

## Consequences

- Adding a vendor that speaks the OpenAI API needs only a `providers` entry. A vendor with its
  own API needs a new provider type in `factory/adapters/llm/`.
- Vendors differ in caching. DeepSeek caches prefixes automatically and reports
  `prompt_cache_hit_tokens`. The stable-first prompt order from architecture §8 applies to
  every provider.
- Qwen prices are not filled in yet; the third-party listings found on 2026-10-11 disagree.
  Fill them in from the Model Studio pricing page.
