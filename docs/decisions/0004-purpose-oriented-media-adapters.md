# ADR 0004: Purpose-oriented media adapters

- **Date:** 2026-11-01
- **Status:** accepted
- **Decided by:** the user (project owner)
- **Builds on:** [ADR 0003](0003-real-media-and-publish-providers.md), which picked the vendors.
  This record fixes how stations reach them. LLM routing follows the same pattern
  ([ADR 0002](0002-per-role-llm-providers.md)).

## Decision

Stations depend on what a media step is for, never on who provides it. Each purpose has one
protocol in its own package under `factory/adapters/`:

| Purpose | Protocol | Station | Providers (`type` in `config/media.yaml`) |
|---|---|---|---|
| Speech | `speech.base.SpeechSynthesizer` | C4 TTS | `fake_speech`, `azure_speech` |
| Image | `image.base.ImageGenerator` | C6 images | `fake_image`, `cloudflare_workers_ai`, `deepinfra` |
| Video | `video.base.VideoRenderer` | C8 render | `ffmpeg_pillow` |
| Publishing | `publishing.base.VideoPublisher` | C10 upload and schedule | `export`, `youtube` |

- **Neutral requests.** `SpeechRequest(text, language, voice, rate)` carries an abstract voice
  key and a rate relative to the pack's native speaking rate (1.0 = native); the voice worker
  converts the pack's unit (wpm, mora/s, ...) so no provider needs to know the pack.
  `ImageRequest(prompt, width, height, seed)` asks for an exact size; a provider that draws
  another size crops and scales with the shared `fit_image`.
- **Abstract voices.** A pack declares `VoiceSpec(key, locale, gender, tags)`; a channel's cast
  member may pin a key (`cast[].voice`); a media profile maps each key to the provider's voice id.
  Changing the speech provider changes only that map. Contracts and packs hold no vendor voice ids
  (`VoiceDirectives` 2.0.0 has `voice`, not `vendor`/`voice_id`).
- **Costs.** Speech and image calls return `Charge(vendor, model, usd, priced)`, priced from
  `config/media.yaml` `prices`; the station merges them into `CostEntry` rows of the episode's
  ledger. A model without a price runs and is recorded as unpriced. When a request fails halfway
  through a station, the `MediaError` carries what the earlier requests billed, so the ledger stays
  complete across retries. A charge may carry a `dedupe_key`; the ledger stores a keyed charge at
  most once per episode (`cost_ledger.dedupe_key`, unique per episode), so a retry that re-reports it
  does not bill it twice. The voice station keys each line's charge by its artifact folder, its line id
  and the request (synthesizer identity, text, language, voice, rate), so a repeated phrase is still
  two charges, and reuses a line whose WAV and sidecar are
  complete instead of synthesizing it again.
- **Supported rates.** Every synthesizer declares `rate_range`. A rate outside it is an error, never
  clamped: the voice station checks every line before the first request and escalates, because the
  fix is in the level band or the pack's native rate, not in a retry.
- **Provider billing units.** A provider that bills East Asian wide and fullwidth characters as more
  than one (Azure bills them as two) takes the factor from its `options` in `config/media.yaml`
  (`wide_char_units`). The count follows each character's Unicode width, never the language code.
- **Transient failures.** The Azure adapter retries throttling, `ServiceTimeout`,
  `ConnectionFailure` and `ServiceUnavailable` within one attempt budget with capped exponential
  backoff; other errors (authentication, bad SSML, `ServiceError`) fail at once. A failed request is
  not charged. The duration of a line comes from the frames of the WAV written, not from what the
  service reports.
- **Profiles.** `config/media.yaml` names providers (type, model, the environment variables that
  hold their secrets, options) and profiles that pick one provider per purpose. `fake` is the
  default and what CI runs; `live` uses the ADR 0003 vendors. Choose one with
  `factory run --media-profile` or `$FACTORY_MEDIA_PROFILE`. The episode records its profile when
  it is created (`episode.media_profile`); a resumed run keeps it and refuses a different one, so an
  episode is never voiced by one profile and published by another. Dev, staging and production
  differ only in `.env` (separate resources, tokens and channels), as ADR 0003 requires.
- **Identity.** Every provider exposes `identity`: the provider type, model and every setting that
  changes the output (voice map, sample rate, draw size, style suffix, FFmpeg and Pillow versions).
  It is part of the station's `station_version`, so changing the provider never reuses an old
  artifact.
- **No automatic fallback.** When a provider runs out of quota, its error says which config entry
  to switch. Silent fallback would change voices or picture style mid-season.
- **Conformance.** `tests/adapters/conformance.py` holds one check per purpose that every provider
  must pass (WAV format and duration agreement, ordered word timings, exact PNG size, H.264 + AAC
  output of the stated duration, upload then schedule twice). Real providers run it against mocked
  transports in CI and against the real service in tests marked `live`, which run only with
  `FACTORY_LIVE_TESTS=1`.

## Adding a provider

1. Write one module in the purpose's package that implements the protocol and takes its client
   as an optional argument, so tests can inject a mock.
2. Add its `type` to `PURPOSES` and `ProviderConfig.type`, and a branch in the purpose's builder
   in `factory/adapters/media.py`.
3. Add a provider entry (and a price) in `config/media.yaml`.
4. Run the purpose's conformance check against a mock, and a `live` test against the service.

No station, worker, contract or pack changes. A check in the plan's success criteria keeps vendor
names out of `factory/workers`, `factory/contracts`, `factory/orchestrator` and `packs`.

## Consequences

- `factory media voices`, `factory media check speech|image|video|publishing` and
  `factory media auth youtube` exercise one provider at a time, so a smoke test runs through the
  same adapter code an episode uses.
- YouTube upload idempotency no longer depends only on the stored receipt. Before the first byte
  leaves, the upload station commits a marker (`publish_attempt`, one per episode and platform); the
  receipt replaces it in one transaction. With a receipt, the video is up. With a marker and no
  receipt, a run died mid-upload: the station looks for the episode among the channel's 50 latest
  uploads by its `ep-<episode_id>` tag a few times, a minute apart, and escalates when it cannot find
  it. It never uploads while a marker stands. An error the platform raised before receiving anything
  (refused token, exhausted quota, a failed lookup, a refused upload session) clears the marker so the
  retry may upload. An operator settles an escalated upload with
  `factory publish resolve <episode> --platform <p> --external-id <id>` (the video must belong to the
  token's channel) or `--not-uploaded`; either records one job and moves the episode to `UPLOADED` or
  back to `FINAL_APPROVED`. Scheduling sets the audience and synthetic-media labels from the package
  again, because `videos.update(part=status)` replaces the whole status, and a receipt already
  scheduled at the same time is not scheduled again.
  `quota_units` on the receipt counts the 10,000-unit bucket; `videos.insert` draws on the
  separate upload bucket.
- Compliance counts the `ep-<episode_id>` tag against YouTube's 500-character tag limit, so a package
  that only fits without it stops before gate 2 instead of failing at upload.
- The voice worker no longer assigns voices by cast order alone: a cast member's pinned key wins,
  so a female host cannot get a male voice by accident.
