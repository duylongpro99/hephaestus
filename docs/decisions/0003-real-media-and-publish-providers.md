# ADR 0003: Real media and publish providers

- **Date:** 2026-11-01
- **Status:** accepted
- **Decided by:** the user (project owner)
- **Resolves:** [ADR 0001](0001-first-slice-and-spike-scope.md) decision 4 (host voice). Decision 5
  (business model) stays deferred.
- **Evidence:** `plans/reports/researcher-261031-1125-real-provider-selection.md` (sources read
  2026-10-31; claims marked ⚠️ or ❓ there are not yet verified).

## Context

The walking skeleton runs every station with fake TTS, image and publish adapters and an FFmpeg
placeholder video. This record picks the real vendors that replace those fakes for the first slice
(`en` × adult × A2). LLM routing is already set by [ADR 0002](0002-per-role-llm-providers.md).

Constraints set by the user:

- **No local model inference.** There is no hardware for it, so only hosted APIs are used. Plain CPU
  tooling (FFmpeg encode, Pillow drawing) still runs locally.
- **Free tier first.** Lower quality is accepted now; vendors are upgraded once there is revenue.
- **Production budget:** about $3–5 per month at 30 episodes of about 5 minutes, paid by card.

## Decision

### Production

| Area | Provider | Fallback | Upgrade path | Cost per month |
|---|---|---|---|---|
| TTS | Azure AI Speech **S0**, Neural voices | Amazon Polly Neural (`en` only) | Azure Neural HD (DragonHD), then ElevenLabs v3 | ≈ $2.4 |
| Alignment | none needed: Azure returns `WordBoundary` events | Whisper large-v3-turbo on Cloudflare Workers AI | Deepgram Nova-3 | $0 |
| Image | FLUX.2 [klein] 4B on Cloudflare Workers AI (free 10K neurons/day) | same model on DeepInfra | Gemini image (Nano Banana 2) or BFL API | $0 (≈ $2.4 on fallback) |
| Render | FFmpeg + Python, text and subtitles drawn with Pillow | Remotion on CPU (Free License) | Remotion Company License or Lambda | $0 |
| Publish | YouTube Data API v3 | export package for manual upload in YouTube Studio | quota audit, then podcast RSS | $0 |

- **Host voice:** en-GB Azure Neural voices, so Anna keeps her Manchester bio. Each cast member's
  voice is pinned; there is still no automatic voice fallback (architecture §12).
- **Support language audio:** `vi` lines are on-screen text only in the first slice; no `vi` TTS.
- **Render:** Remotion is deferred. The first slice keeps the FFmpeg path the skeleton already uses.
  The local Homebrew FFmpeg has no `libass`/`freetype`, so text is drawn with Pillow and overlaid.
- **Synthetic media:** `containsSyntheticMedia` stays `true`, and the video description must also
  say the voices are AI-generated (the packager does not add this line yet). Together they cover
  YouTube's disclosure rules and Microsoft's AI Code of Conduct.

### Testing environments

Dev and staging may use free tiers **even when their terms forbid commercial use**, because their
output is never published publicly. Hosted APIs only, as in production.

| Area | Dev | Staging |
|---|---|---|
| TTS | fake adapter in CI; Azure **F0** for manual smoke tests | Azure F0, a resource separate from production S0 |
| Image | fake adapter in CI; Cloudflare free for smoke tests | Cloudflare free, a token separate from production |
| Render | FFmpeg + Pillow | FFmpeg + Pillow |
| Publish | no upload; export package | YouTube Data API v3 to a **private staging channel** in its own Google Cloud project |

Azure F0 uses the same Neural voices, SSML `prosody rate` and `WordBoundary` as S0, and Cloudflare
free runs the same image model, so a Gate 1 preview on staging represents production. That stops
holding if production moves to HD voices, which F0 does not offer. Other free TTS tiers (Polly via
the AWS Free plan, ElevenLabs Free, Gemini free, Cartesia) produce different voices and are only
for testing pipeline behaviour, not for judging voice quality.

## Consequences

- **TTS adapter** uses the Azure Speech SDK, since `WordBoundary` comes over the SDK's WebSocket and
  the REST API returns audio only. The pack's `wpm` rate maps to SSML `prosody rate` (0.5–2×), so
  slow lines are re-synthesised, never time-stretched. Its `identity` names the region and voice.
  The `en` pack needs a real voice roster.
- **F0 throttling:** 20 transactions per 60 s and 0.5M characters per month. A staging episode of
  about 80 lines takes about 4 extra minutes; that is accepted.
- **Image adapter** calls the Cloudflare REST API with an account id and API token. A free-plan
  quota error fails the request and does not bill; the operator switches to DeepInfra in config.
  Prompts must avoid real people, brands and copyrighted characters, and thumbnail text is drawn by
  the renderer, not by the model.
- **YouTube quota:** uploads have their own bucket since 2026-06-01, so an episode costs about 950
  units of the 10K daily budget (architecture §12).
- **OAuth:** an app in "Testing" status gets refresh tokens that expire after 7 days. That is
  acceptable on staging; production moves the app to "In production".
- **Secrets:** Azure, Cloudflare and Google keys are per environment and live in `.env` or the
  secret store, never in the repo.

### Risks accepted

- **Non-commercial output reaching production.** The user decided not to add a code guard that
  blocks free-tier output from being published. Separation relies on separate resources, keys and
  channels per environment.
- **Unaudited YouTube projects** may force uploads to private. Official pages conflict; the staging
  channel tests whether `publishAt` works before production relies on it, and the manual-upload
  export is the fallback.
- **Unverified terms and prices:** Azure S0 prices come from third-party sources; F0's lack of
  commercial output rights comes from Microsoft Q&A moderators; BFL's terms (which Cloudflare
  requires for FLUX) have not been read. Check Azure prices in the portal when creating the
  resource and read the BFL terms before the first real image.

### To verify at the first smoke test

Results are recorded in `plans/reports/smoke-261101-media-providers.md`; the adapters are in
place ([ADR 0004](0004-purpose-oriented-media-adapters.md)) and each item runs with
`factory media check ...`.

- `WordBoundary` events arrive on an F0 resource. *Pending: needs an F0 key.*
- `prosody rate` at the A2 slow rate sounds natural with the chosen en-GB voices. *Pending.*
- Cloudflare's free plan accepts REST calls and the image cost per 1024×576 matches the estimate.
  *Pending: needs a Cloudflare account.*
- Render time for a 5-minute episode on the local laptop. **Verified 2026-11-01:** 22 s for 300 s
  of 1920×1080 video with 80 captions on an Apple M1 Pro (4.3 MB, about 1.8 GB peak memory).
