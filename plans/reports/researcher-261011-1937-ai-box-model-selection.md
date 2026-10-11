# AI Box model selection per factory role

- **Date:** 2026-10-11 (all live data was fetched on this date, around 19:40 ICT)
- **Scope:** the AI Box gateway (`https://api.ai-box.vn/v1`) catalog, and a model choice for
  `a2_scriptwriter`, `a3_level_editor`, `review_examiner` and `review_learner`.
- **Constraint:** there was no API key. The catalog and prices come from AI Box's own public,
  unauthenticated endpoints; behavior under load comes from vendor docs and is unverified here.

## Outcome

1. **The current `config/llm.yaml` will not run on AI Box.** Neither `deepseek-v4-pro` nor
   `qwen3-max` is in the live catalog. The DeepSeek model is `ds/deepseek-v4-pro`. There is no
   `qwen3-max`; the current Qwen flagships are `qwen3.8-max` / `qwen3.8-max-0902` and `qwen3.7-max`.
   The homepage code samples (`deepseek-v4-pro`, `claude-4-7-opus`) are out of date: neither
   appears in the pricing list.
2. **Recommended routing:** use three families, one per job.
   - Writer and editor: `ds/deepseek-v4-pro` (DeepSeek).
   - Examiner: `kimi/kimi-k3` (Moonshot).
   - Learner: `qwen3.8-max-0902` (Qwen).
3. **Estimated cost:** about **$0.13 per script** (around 3,300 VND) in a typical run, and about
   **$0.26** (around 6,800 VND) in the worst case where A3 uses all 4 turns × 15 tool calls. The
   10-script spike costs roughly $1.3–2.6.
4. **The biggest risk is the gateway, not the models.**
   - AI Box opens new registrations only in short windows.
   - Its prices are about 1/3 to 1/5 of the vendors' list prices, which points to resold capacity.
   - It silently reroutes `ds/*` models to Alibaba-hosted copies when its DeepSeek supply runs out.
   - It announces model changes only on Telegram.

## 1. What AI Box is

AI Box is a **new-api** deployment (the QuantumNous fork of One API), with Vietnamese branding:

- `api.ai-box.vn/v1/models` without a key returns `{"type":"new_api_error"}`.
- `home.ai-box.vn/api/status` reports `system_name: "API AI BOX"`.

The bare `ai-box.vn` domain serves a different app: a rebranded xiaozhi-esp32 voice-device
console. It is not the gateway's site, and it holds no catalog.

| Fact | Value | Source (fetched 2026-10-11) |
|---|---|---|
| Base URL | `https://api.ai-box.vn/v1`; only the `openai` endpoint type (`/v1/chat/completions`) appears in pricing. The site also claims Anthropic SDK compatibility. | `https://home.ai-box.vn/api/pricing` (`supported_endpoint`), `https://home.ai-box.vn/api/home_page_content` |
| Currency | Billing is in VND. 1 internal USD unit costs 26,000 VND (`custom_currency_exchange_rate` / `sepay_unit_price` = 26000). The FAQ's "1 Quota = 1 VNĐ" refers to the displayed unit. | `https://home.ai-box.vn/api/status` |
| Price formula | new-api: `model_ratio` 1 = $0.002 per 1K tokens = **$2 per M input**. Output = input × `completion_ratio`. Cached input = input × `cache_ratio`. | new-api source [`setting/ratio_setting/model_ratio.go`](https://github.com/QuantumNous/new-api/blob/main/setting/ratio_setting/model_ratio.go) (line comment "1 === $0.002 / 1K tokens"), [`common/constants.go`](https://github.com/QuantumNous/new-api/blob/main/common/constants.go) `QuotaPerUnit = 500*1000` |
| Groups | Only `default` (group ratio 1) is shown publicly. A `Vip` group gets a 15% discount (Telegram, 2026-09-15). | `/api/pricing`, [t.me/s/apiaibox](https://t.me/s/apiaibox) |
| Docs | `docs_link` points to `https://api.ai-box.vn/docs`, which redirects to `home.ai-box.vn/docs`, a page that renders no docs. **There are no public docs on JSON mode, tools or param pass-through.** | `/api/status`, curl |
| Change channel | Since 2026-09-10, model changes are announced **only** on Telegram (`t.me/apiaibox`). | `/api/status` announcements |

### Catalog relevant to these roles

The prices below are in internal USD per million tokens. Multiply by 26,000 to get the VND
actually charged. Every row comes from `https://home.ai-box.vn/api/pricing`, fetched 2026-10-11,
using the formula above. The list also has image, video, embedding, rerank and OCR models, which
are omitted here.

| Model id (exact) | Vendor | Input | Cached input | Output | Vendor list price (in / out) |
|---|---|---|---|---|---|
| `ds/deepseek-v4-pro` | DeepSeek (origin) | 0.22 | 0.0073 | 0.66 | $0.66–1.32 / $1.98–3.96 (off-peak/peak) [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| `ds/deepseek-flash` | DeepSeek (origin) | 0.05 | 0.001 | 0.20 | $0.15–0.30 / $0.60–1.20 (same page) |
| `qwen3.8-max` | Alibaba | 0.40 | 0.025 | 1.20 | $2 / $6 (reported, [noze.it](https://www.noze.it/en/insights/qwen-3-8-max/)) |
| `qwen3.8-max-0902` | Alibaba (pinned snapshot) | 0.40 | 0.025 | 1.20 | same |
| `qwen3.7-max` | Alibaba | 0.25 | 0.05 | 0.75 | — |
| `qwen3.7-plus` | Alibaba | 0.064 | 0.0128 | 0.265 | — |
| `qwen3.8-flash` | Alibaba | 0.032 | 0.0032 | 0.094 | — |
| `kimi/kimi-k3` | Moonshot (likely origin) | 0.60 | 0.06 | 3.00 | $3 / $15 ([AA comparison](https://artificialanalysis.ai/models/comparisons/kimi-k3-vs-deepseek-v4-pro)) |
| `kimi-k3` | Moonshot (likely Alibaba-hosted) | 0.60 | 0.06 | 3.00 | same |
| `ZHIPU/GLM-5.3` | Z.ai (origin) | 0.28 | 0.052 | 0.88 | — |
| `glm-5.3` | Z.ai (Alibaba-hosted, "faster", Telegram 2026-09-15) | 0.28 | 0.052 | 0.88 | — |
| `glm-5.3-prime` | Z.ai | 0.56 | 0.112 | 1.76 | — |
| `kimi-k2.7-code` | Moonshot | 0.19 | 0.038 | 0.80 | — |

The catalog has **no OpenAI, Anthropic or Google chat models**, although those vendors appear in
the vendor list. If Claude exists, it is in a hidden group or behind the Anthropic endpoint; it
is unconfirmed. The naming pattern is my inference from the Telegram posts: a vendor prefix
(`ds/`, `kimi/`, `ZHIPU/`) means the vendor's own API, and a bare id means Alibaba Model Studio
hosting.

### Feature support through the gateway

| Feature | Upstream vendor | new-api (gateway software) | AI Box deployment |
|---|---|---|---|
| `response_format: json_object` | DeepSeek: yes ([API ref](https://api-docs.deepseek.com/api/create-chat-completion)). Qwen: yes, but third-party tests say to turn thinking off for structured output ([APIYI](https://docs.apiyi.com/en/api-capabilities/qwen-3-8/overview)). Kimi K3: third-party guides only ([apidog](https://apidog.com/blog/kimi-k3-api/)). | Field present in the request DTO ([`relaykit/dto/openai_request.go`](https://github.com/QuantumNous/new-api/blob/main/relaykit/dto/openai_request.go) L52) | **Unverified** |
| `tools` / `tool_choice` | All four families support OpenAI-style tools | DTO L56–57 | **Unverified** |
| `reasoning_content` echoed back in messages | DeepSeek **requires** it on every follow-up when `tools` are present, or it returns 400 ([thinking mode](https://api-docs.deepseek.com/guides/thinking_mode)). Kimi K3 asks for it too ([Kimi docs](https://platform.kimi.ai/docs/guide/use-thinking-models)). | Message field `reasoning_content` (DTO L476) | **Unverified** |
| `thinking`, `reasoning_effort`, `enable_thinking` | DeepSeek: `thinking:{type}` and `reasoning_effort` none/low/high/max. Qwen: `enable_thinking` / `reasoning_effort`. Kimi K3 and GLM-5.3: reasoning is always on. | DTO L39, L92, L102 | **Unverified**; channel param overrides may change them |

## 2. Per-role ranking

Evidence quality is weak across the board. Every 2026 model here has mostly vendor-reported
benchmarks. Artificial Analysis (AA) is the only independent evaluator that covers all of them,
and its scores measure reasoning and agentic work, not EFL writing or Vietnamese. **No
public benchmark measures English↔Vietnamese naturalness for these models.** The 10-script spike
is the real evaluation.

### a2_scriptwriter

| Rank | Model | Why |
|---|---|---|
| **1** | `ds/deepseek-v4-pro` | It has official JSON mode and a 384K max output ([API ref](https://api-docs.deepseek.com/api/create-chat-completion)), the most headroom for a 15K-token JSON plus reasoning. In DeepSeek's own report it wins 77% on writing quality against Gemini, but trails Claude Opus 4.5 on complex instruction following ([arXiv 2606.19348](https://arxiv.org/pdf/2606.19348)). It scores 76.5% on IFBench ([modelgrep](https://modelgrep.com/best/instruction-following/deepseek)). It is the cheapest strong model in the catalog. Keeping the writer on DeepSeek also leaves Qwen, the best Vietnamese evidence, free for the learner reviewer. |
| 2 | `qwen3.8-max-0902` | It has the higher instruction-following claim (IFBench 82.8, vendor-reported, [noze.it](https://www.noze.it/en/insights/qwen-3-8-max/)) and likely stronger Vietnamese, which matters because the writer produces every Vietnamese line. Against it: AA rates it "very verbose", one AA report shows its hallucination rate rising from 23% to 40% ([noze.it](https://www.noze.it/en/insights/qwen-3-8-max/)), JSON mode with thinking on is reported to be fragile, and using it here pushes the learner reviewer onto a weaker-Vietnamese family. |
| 3 | `ZHIPU/GLM-5.3` | AA Intelligence Index 45 ([AA](https://artificialanalysis.ai/models/glm-5-3)) and 128K max output, but reasoning is always on, it is very verbose, and it has no writing-specific evidence. |

There is a known weakness in rank 1: DeepSeek's Vietnamese is the least evidenced of the four
families. On the only multilingual leaderboard found, DeepSeek V3 scores 55.5 against 100 for
Qwen3.7 Max ([BenchLM, verified 2026-10-10](https://benchlm.ai/md/multilingual.md); one benchmark,
MMLU-ProX, an older DeepSeek version). The learner reviewer exists to catch this. If it flags
Vietnamese in most of the 10 scripts, swap the writer to rank 2 and the learner to `ZHIPU/GLM-5.3`.

### a3_level_editor

| Rank | Model | Why |
|---|---|---|
| **1** | `ds/deepseek-v4-pro` | Thinking-mode tool calls are documented officially, and the adapter already sends `reasoning_content` back ([thinking mode](https://api-docs.deepseek.com/guides/thinking_mode)). Using the same model as the writer keeps the voice consistent on patched lines. Its 85 tokens/s is 2× Kimi K3 ([AA](https://artificialanalysis.ai/models/comparisons/kimi-k3-vs-deepseek-v4-pro)), which matters for up to 60 calls per script. |
| 2 | `ds/deepseek-flash` | Same family and API behavior at about 1/4 the price. This is the move-down path after the spike shows the editor's quality holds (architecture §3 policy). |
| 3 | `ZHIPU/GLM-5.3` | Strong agentic scores (vendor DeepSWE 66.9, [datanorth](https://datanorth.ai/news/z-ai-releases-glm-5-3)). Avoid Qwen here: an editor from the learner's family would let the learner judge its own family's edits. |

Two risks apply to this role:

- **Silent rerouting.** AI Box sends `ds/deepseek-v4-pro` to Alibaba's `deepseek-v4-pro-0813`
  when its DeepSeek supply runs out ([Telegram, 2026-10-07 and 10-08](https://t.me/s/apiaibox)).
  The weights are the same version (DeepSeek's own `deepseek-v4-pro` is V4-Pro-0813 per its
  pricing page), but a host switch in the middle of a tool loop may break the `reasoning_content`
  round-trip.
- **Forced tool choice.** DeepSeek in thinking mode rejects a `required` or named `tool_choice`.
  The adapter does not set either, so this is fine today.

### review_examiner (strict native-English ESL examiner)

| Rank | Model | Why |
|---|---|---|
| **1** | `kimi/kimi-k3` | A third family, different from both the writer and the learner. It has the best independent knowledge score in the catalog: AA-Omniscience 20 against DeepSeek V4 Pro's 1, and Intelligence Index 44 against 36 ([AA](https://artificialanalysis.ai/models/comparisons/kimi-k3-vs-deepseek-v4-pro)). Reasoning is always on, which suits a strict judge. It is the most expensive model at about $0.04 per review, which is still small. |
| 2 | `ZHIPU/GLM-5.3` | Also a third family, with AA index 45 and lower cost. It is very verbose, and AA lists it with 210M output tokens on its index ([AA](https://artificialanalysis.ai/models/glm-5-3)). Use it if Kimi K3's JSON mode fails. |
| 3 | `qwen3.7-max` | Strong, but it is the learner's family, so the two personas would share blind spots. Use it only if the first two both fail. |

No public benchmark measures "native-English collocation judgment". AA scores are proxies, and
the user's spot-check of 2 scripts (ADR 0001) remains the real check.

### review_learner (Vietnamese A2 learner)

| Rank | Model | Why |
|---|---|---|
| **1** | `qwen3.8-max-0902` | The Qwen family has the strongest multilingual evidence: Qwen3.7 Max is #1 on BenchLM's multilingual board ([BenchLM](https://benchlm.ai/md/multilingual.md)), and the Qwen3 technical report covers 119 languages including Vietnamese ([arXiv 2505.09388](https://arxiv.org/pdf/2505.09388)). It is not the writer's family or the examiner's. The pinned snapshot keeps `station_version` honest. |
| 2 | `qwen3.7-max` | It is the model that actually has the multilingual score above. It is cheaper ($0.25 / $0.75) and less verbose than 3.8 by reputation. Use it if `qwen3.8-max-0902` has JSON or availability trouble. |
| 3 | `ZHIPU/GLM-5.3` | GLM-5 scores 89.5 on the same board. It is the fallback if Qwen supply runs dry: AI Box said on 2026-09-18 that "the Ali source is running low". |

## 3. Ready-to-paste config

The `params` are empty on purpose. AI Box publishes no docs confirming that `thinking`,
`reasoning_effort` or `enable_thinking` pass through to the upstream. new-api's request DTO
declares them, but a channel may override them. The `max_tokens` values are raised because
reasoning tokens consume the output budget:

- DeepSeek's thinking-mode **default** `max_tokens` is 64K, and 128K at `max` effort
  ([API ref](https://api-docs.deepseek.com/api/create-chat-completion)).
- AA measured about 38K reasoning tokens per task for DeepSeek V4 Pro and 32K for Kimi K3.
- The adapter raises `LLMError` on `finish_reason == "length"`.

```yaml
prices:
  gateway:   # internal USD per M tokens; AI Box bills 26,000 VND per unit (home.ai-box.vn/api/pricing, 2026-10-11)
    ds/deepseek-v4-pro: {input: 0.22,  cached_input: 0.0073, output: 0.66}
    ds/deepseek-flash:  {input: 0.05,  cached_input: 0.001,  output: 0.20}
    qwen3.8-max-0902:   {input: 0.40,  cached_input: 0.025,  output: 1.20}
    qwen3.8-max:        {input: 0.40,  cached_input: 0.025,  output: 1.20}
    qwen3.7-max:        {input: 0.25,  cached_input: 0.05,   output: 0.75}
    kimi/kimi-k3:       {input: 0.60,  cached_input: 0.06,   output: 3.00}
    kimi-k3:            {input: 0.60,  cached_input: 0.06,   output: 3.00}
    ZHIPU/GLM-5.3:      {input: 0.28,  cached_input: 0.052,  output: 0.88}
    glm-5.3:            {input: 0.28,  cached_input: 0.052,  output: 0.88}

roles:
  a2_scriptwriter:
    provider: gateway
    model: ds/deepseek-v4-pro
    max_tokens: 64000       # reasoning + ~15K-token JSON; DeepSeek's own thinking-mode default
    params: {}
  a3_level_editor:
    provider: gateway
    model: ds/deepseek-v4-pro
    max_tokens: 16000
    params: {}
  # Three families: DeepSeek writes, Moonshot examines, Qwen reads as the learner (ADR 0001, decision 3).
  review_examiner:
    provider: gateway
    model: kimi/kimi-k3
    max_tokens: 32000       # K3 reasoning is always on (~32K reasoning tokens/task on AA)
    params: {}
  review_learner:
    provider: gateway
    model: qwen3.8-max-0902
    max_tokens: 32000
    params: {}
```

If `qwen3.8-max-0902` rejects `json_object` while thinking is on, the first param to test is
`enable_thinking: false` (or `reasoning_effort: "none"`). Keep it only if a real call shows it took
effect, for example through the reasoning tokens reported in usage.

## 4. Cost per script (recommended setup)

The token assumptions start from architecture §8, corrected for two things §8 leaves out:
reasoning tokens, and the per-iteration resend inside A3's tool loop. Input prices assume no
cross-script cache hits, which is conservative. Within an A3 loop, 85% cached is assumed,
because the message list only grows by appending.

| Station | Typical tokens | Typical $ | Worst-case tokens | Worst $ |
|---|---|---|---|---|
| A2, DeepSeek V4 Pro | 15K in / 25K out (15K JSON + ~10K reasoning) | 0.020 | +1 repair round | 0.040 |
| A3, DeepSeek V4 Pro | 4 turns × 6 calls × ~30K in (85% cached) / 1.5K out | 0.052 | 4 × 15 calls × ~35K in / 2K out | 0.161 |
| Examiner, Kimi K3 | 20K in / 8K out | 0.036 | same | 0.036 |
| Learner, Qwen3.8 Max | 20K in / 8K out | 0.018 | same | 0.018 |
| **Total per script** | | **≈ $0.13 (≈ 3,300 VND)** | | **≈ $0.26 (≈ 6,800 VND)** |

- At vendor list prices (DeepSeek peak, Kimi $3/$15, Qwen $2/$6) the same run costs about 5–6×
  more, roughly $0.65–1.40 per script. That is AI Box's real advantage, and its real
  sustainability question.
- At 10–30 episodes a week, the script stage costs $1.3–8 a week. Cost does not drive the
  choice at this volume; quality and gateway reliability do.

## 5. To verify with `uv run factory models gateway` and one smoke call per role

1. The key's group returns the ids above, including the exact casing of `ZHIPU/GLM-5.3`, and
   whether the key is in `default` or `Vip` (15% off).
2. `json_object` works on each recommended model with thinking on. Qwen3.8 Max and Kimi K3 are
   the doubtful ones.
3. A DeepSeek tool loop over 3 or more iterations does not return 400. This shows that
   `reasoning_content` survives the gateway in both directions.
4. Whether `thinking`, `reasoning_effort` and `enable_thinking` reach the upstream. Compare
   `usage.completion_tokens_details.reasoning_tokens` with the param set and unset.
5. Which usage shape the gateway returns for cached tokens (`prompt_cache_hit_tokens` or
   `prompt_tokens_details.cached_tokens`), so that costs are priced correctly.
6. The response `model` field, to see whether a fallback such as `deepseek-v4-pro-0813` shows up
   in the recorded cost entries. The adapter already records `response.model`.
7. Whether Claude models (`claude-4-7-opus` in the homepage sample) exist for this key.
   Architecture §3 wanted a Claude judge on A4. If Claude exists, it would be the strongest
   examiner candidate.
8. The real per-call VND deduction in the AI Box log, compared with the computed prices.

## 6. Limitations

- I could not call the API, so all feature support at the AI Box layer is inferred from upstream
  docs and new-api source. That source is the current `main`; AI Box's version string is empty.
- No independent English↔Vietnamese quality evaluation of DeepSeek V4, Qwen3.8, Kimi K3 or
  GLM-5.3 exists publicly. The Vietnamese ranking rests on one multilingual leaderboard built on
  a single benchmark and on Qwen's documented language coverage.
- Most 2026 benchmark figures are vendor-reported. AA numbers differ between AA pages, depending
  on the index version, so treat them as ordinal only.
- I did not assess AI Box's terms, data retention or legal standing. It says it does not log
  prompts; this cannot be verified. The scripts hold no personal data, so the exposure is low.

## Unresolved questions

1. Do you already have an AI Box account and key? Registration opens only in short windows: it
   was closed on 2026-09-11 and 09-15, and open until 2026-10-03. If you have no key, the first
   routing step is blocked.
2. Do you accept the reseller risk for production volume? This means silent upstream swaps,
   supply shortages, and Telegram-only change notices. Or should a direct vendor provider
   (DeepSeek or Model Studio) be the fallback in `providers`?
3. Should the learner stay on Qwen even though the writer then has weaker Vietnamese evidence
   (§2)? Or should the spike A/B 2–3 scripts with `qwen3.8-max-0902` as the writer?
4. Is `kimi/kimi-k3` really the Moonshot origin and `kimi-k3` the Alibaba-hosted copy? This is
   inferred from the naming pattern; ask in the AI Box Telegram group.

Status: DONE_WITH_CONCERNS
Summary: AI Box is a new-api gateway whose live catalog (DeepSeek, Qwen, GLM, Kimi; no Claude/GPT publicly) makes the current config ids invalid; recommended routing is ds/deepseek-v4-pro (writer, editor), kimi/kimi-k3 (examiner), qwen3.8-max-0902 (learner) at about $0.13–0.26 per script. JSON mode, tool calls and param pass-through at the AI Box layer, and account availability, remain unverified without a key.
