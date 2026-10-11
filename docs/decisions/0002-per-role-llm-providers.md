# ADR 0002: Per-role LLM providers

- **Date:** 2026-10-11
- **Status:** accepted
- **Decided by:** the user (project owner)
- **Supersedes:** the single-vendor model policy in [architecture.md §3](../architecture.md), for how
  each role's model is chosen. The roles themselves and their inputs and outputs are unchanged.

## Decision

Each factory role (A2 Scriptwriter, A3 Level Editor, the review personas, and later roles) gets
its own LLM provider and model. Routing lives in [`config/llm.yaml`](../../config/llm.yaml):

- `providers`: each endpoint's type, its URL (`base_url`, or `base_url_env` to read it from the
  environment), and the **name** of the environment variable holding its key. Keys are never
  written to a file.
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

All roles go through one provider, `gateway`: the user's own OpenAI-compatible endpoint. Its
URL and key are read from `LLM_GATEWAY_URL` and `LLM_GATEWAY_API_KEY`, set in the shell or in
the gitignored `.env` (see `.env.example`). `uv run factory models gateway` lists the model
names the endpoint offers.

| Role | Model (to confirm against the gateway's list) |
|---|---|
| a2_scriptwriter | deepseek-v4-pro |
| a3_level_editor | deepseek-v4-pro (needs tool calls) |
| review_examiner | qwen3-max |
| review_learner | qwen3-max |

The reviewers use a different model family from the writer, so the panel does not judge its
own family's output, the main risk in [ADR 0001](0001-first-slice-and-spike-scope.md)
decision 3. The two personas still share one model.

## Consequences

- Adding a vendor that speaks the OpenAI API needs only a `providers` entry. A vendor with its
  own API needs a new provider type in `factory/adapters/llm/`.
- Vendors differ in caching. DeepSeek caches prefixes automatically and reports
  `prompt_cache_hit_tokens`. The stable-first prompt order from architecture §8 applies to
  every provider.
- Gateway prices are not filled in yet, so costs are recorded as tokens with `priced: false`
  until the gateway's per-model prices are added under `prices.gateway`.
- A provider's URL can come from the environment (`base_url_env`) as well as its key, so a
  private endpoint's address is not committed either.
