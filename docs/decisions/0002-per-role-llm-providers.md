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

All roles go through one provider, `gateway`: AI Box (`https://api.ai-box.vn/v1`), an
OpenAI-compatible reseller gateway chosen by the user. Its URL and key are read from
`LLM_GATEWAY_URL` and `LLM_GATEWAY_API_KEY`, set in the shell or in the gitignored `.env` (see
`.env.example`). `uv run factory models gateway` lists the model ids the account can use.

| Role | Model | Family |
|---|---|---|
| a2_scriptwriter | ds/deepseek-v4-pro | DeepSeek |
| a3_level_editor | ds/deepseek-v4-pro (needs tool calls) | DeepSeek |
| review_examiner | kimi/kimi-k3 | Moonshot |
| review_learner | qwen3.8-max-0902 | Qwen |

Three model families mean neither reviewer judges its own family's output, the main risk in
[ADR 0001](0001-first-slice-and-spike-scope.md) decision 3. The evidence and alternatives are in
`plans/reports/researcher-261011-1937-ai-box-model-selection.md`.

## Consequences

- Adding a vendor that speaks the OpenAI API needs only a `providers` entry. A vendor with its
  own API needs a new provider type in `factory/adapters/llm/`.
- Vendors differ in caching. DeepSeek caches prefixes automatically and reports
  `prompt_cache_hit_tokens`. The stable-first prompt order from architecture §8 applies to
  every provider.
- Prices come from AI Box's public pricing endpoint, in its internal dollars (billed at 26,000 VND
  each). The gateway is a reseller: it may reroute a model to another host without notice, and
  JSON mode and tool calls through it were verified for all four roles on 2026-10-12.
- The spike uses one provider with no failover. Automatic swapping to another provider when a
  model is unavailable is deferred to production.
- `factory script --writer <role>` drafts with another `roles` entry. A Qwen writer
  (`qwen3.8-max-0902`) was tried on 2026-10-12 and dropped: in JSON-object mode it returned
  structurally broken scripts on every attempt, while it works as the learner reviewer.
- A provider's URL can come from the environment (`base_url_env`) as well as its key, so a
  private endpoint's address is not committed either.
