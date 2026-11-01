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
  complete across retries.
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
- YouTube upload idempotency no longer depends only on the stored receipt: before uploading, the
  publisher looks for the episode among the channel's 50 latest uploads by an `ep-<episode_id>`
  tag, so a crash between upload and receipt does not upload twice. Scheduling sets the audience and
  synthetic-media labels from the package again, because `videos.update(part=status)` replaces the
  whole status.
  `quota_units` on the receipt counts the 10,000-unit bucket; `videos.insert` draws on the
  separate upload bucket.
- The voice worker no longer assigns voices by cast order alone: a cast member's pinned key wins,
  so a female host cannot get a male voice by accident.
