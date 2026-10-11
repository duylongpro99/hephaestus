# Video Factory: Multi-Agent Architecture

This builds on [research.md](research.md). It defines a multi-agent "factory" that turns a curriculum into published, level-graded YouTube episodes for **any target language, any learner age and any proficiency level**.

The factory has no built-in languages, ages or levels. They come from four stacked **configuration layers** (§4.0):
1. **Language Pack**
2. **Level Framework**
3. **Audience Profile**
4. **Channel Bible**

Stations never branch on "Japanese" or "kids". They read the layers.

**EN Podcast, JP Podcast and Kids EN** appear throughout only as *worked examples* that show the configuration layers in use.

Drafted 2026-09-28, generalized 2026-09-29, **hardened 2026-10-03** after an end-user walkthrough (§1.5): Gate 0 for season plans, ad-hoc episodes, roles and notifications, thumbnails and captions as stations, publish idempotency, post-publish lifecycle, data model, operations, licensing register, testing and v1 non-goals. Model IDs and prices come from the Claude API reference as of 2026-09-28. Re-check them before building.

---

## 1. Design principles

1. **Code runs the assembly line and agents work the stations.** The orchestrator is a deterministic state machine: retries, gates, budgets, ordering. An agent is a *bounded* LLM step with a typed input and output. Only stations whose work is genuinely open-ended get a tool loop. Everything else is a single structured-output call. This is cheaper and easier to debug, and a bad output can be replayed station by station.
2. **Each station has a typed contract.** Every station reads and writes versioned JSON artifacts (`EpisodeSpec`, `Script`, `AudioManifest`, …). They are validated against a schema at the station boundary, never passed along as free text.
3. **Checks in code come first, LLM judges second, humans last.** Anything measurable is checked in code: vocabulary coverage, speech rate, reading aids, loudness, quota. LLM judges handle naturalness, pedagogy and policy. Humans approve at two gates.
4. **Originality is a factory output.** YouTube's inauthentic-content policy is the biggest business risk. So each channel has a **Channel Bible** (persona, cast, style, variety rules), and an **Originality Gate** blocks episodes too similar to recent ones.
5. **Idempotent, cacheable, resumable.** Every artifact is content-addressed as `hash(inputs + station version)`. Re-running a station with the same inputs is free, and changing one line re-renders only what depends on it.
6. **Vendors sit behind adapters.** TTS, image, LLM, render and publish each have an interface: the research found real churn (Gemini TTS prices doubling in 2027, the Sora 2 API shutting down, Suno's terms changing).
7. **Language, age and level are data, not code.**
   - Anything that depends on the language is a Language Pack plug-in: tokenizer, reading aids, rate unit, wordlists, voices, script direction.
   - Anything that depends on age is an Audience Profile: pacing, visuals, safety, compliance flags.
   - Level definitions live in a Level Framework mapped to a common scale.
   - Adding "Korean for teens" or "Spanish for seniors" means writing configuration plus one pack, and passing that pack's conformance tests.

8. **Humans can always stop, skip or redo.** Every lane has a pause switch. Every episode can be cancelled, re-run from any station, or patched or retired after publish. Nothing is published without a recorded human decision (`GateDecision`).
9. **Every episode pins its configuration.** The episode stores the `config_hash` of the ResolvedConfig it was produced with. Editing a Bible or a level band mid-season never changes an in-flight episode; the operator chooses whether to re-resolve it (§4.5).
10. **Side effects are idempotent.** Uploads, scheduling, caption inserts and notifications are keyed by episode and station, so a retry never creates a second YouTube video or a second email.

---

## 1.5 Who uses it, and the end-user walkthrough

The factory has four roles. One person can hold all of them on a small channel; permissions are granted per channel.

| Role | Owns | Touches |
|---|---|---|
| **Admin** | workspace, secrets, budgets, Language Packs (via pull requests), pinned model and prompt versions | everything, rarely day to day |
| **Channel operator** | Channel Bible, seasons, publish calendar, Gate 0 and Gate 2 | the console daily |
| **Native reviewer** (per pack) | Gate 1 for scripts in their language | the script review screen only; may be an external contractor |
| **Analyst / viewer** | nothing | dashboards and Analyst proposals, read-only |

**The walkthrough the design must serve.** Nobody "makes a video". An operator configures a channel once, approves a season plan, and then works a queue.

| Step | Who | What they do | Hands-on time |
|---|---|---|---|
| 0. Set up a channel | admin + operator | pick Pack, Framework + levels, Audience Profile; write the Channel Bible; connect the YouTube account; set budgets, cadence and time zone; assign reviewers | hours to days, once |
| 1. Plan a season | operator | run Showrunner, edit loglines, approve (**Gate 0**); C1 then emits 10–12 EpisodeSpecs | about 30 min per season |
| 1b. Ad-hoc episode | operator | type a theme, optional target words and format; one EpisodeSpec with `source: adhoc` is created and C1 fills its review slots from the ledger | 5 min |
| 2. Script written and self-checked | factory | A2 → A3 → C2 → A4/A5 → C3 | none (minutes to hours; batchable overnight) |
| 3. **Gate 1**: approve the script | native reviewer | line-by-line view, judge issues inline, per-line audio preview; approve, edit-and-approve, or reject with notes | ≤15 min podcast, ≤25 min kids |
| 4. Voice, visuals, render, visual QA | factory | A6 → C4/C5 → A7 → C6/C14 → C7/C8 → A8/C9 | none (10–30 min) |
| 5. Package | factory | A9, A10, C12 thumbnails, C13 captions, A11 compliance | none |
| 6. **Gate 2**: final watch and publish | operator | player, rendered thumbnails, metadata shown as a YouTube card preview, compliance checklist, publish slot; approve | 10–25 min |
| 7. Upload and schedule | factory | C10 uploads private, stores the receipt, then sets `publishAt` | none |
| 8. After publish | factory; operator reads | C11 collects at +7 and +28 days; A12 proposes tuning weekly; the operator applies it by editing config | minutes per week |

Design consequences of the walkthrough, all addressed below: a season plan needs its own gate (§5); episodes must be creatable outside a season (§4.2); thumbnails and captions are stations, not afterthoughts (§7); Gate 1 and Gate 2 are usually different people, so assignment and notification are part of the system (§9); and operators must be able to pause, cancel, re-run and patch after publish (§5, §11).

---

## 2. Factory floor overview

```
                         ┌─────────────────────────────────────────────────────────┐
                         │                  ORCHESTRATOR (code)                    │
                         │  season + episode state machines · job queue · budgets  │
                         │  retries · artifact store (content-addressed) · Postgres│
                         │  [C15] Notifier · [C16] Publish calendar · lane pause   │
                         └───────┬───────────────────────────────────────┬─────────┘
                                 │ dispatches work orders                │ events/metrics
                                 ▼                                       ▼
 ┌────────────────────── PRE-PRODUCTION (per season) ──────────────────────┐
 │  [A1] Showrunner ──▶ SeasonPlan ──▶ ██ HUMAN GATE 0: plan approval ██   │
 │                                     └─▶ [C1] Scheduler ─▶ EpisodeSpec×N │
 │  Operator "ad-hoc episode" form ─▶ EpisodeSpec(source=adhoc) ─▶ [C1]    │
 └─────────────────────────────────────────────────────────────────────────┘
                                 │
 ┌────────────────────── WRITERS' ROOM (per episode) ──────────────────────┐
 │  [A2] Scriptwriter ─▶ Script v1                                         │
 │        ▼                                                                │
 │  [A3] Level Editor (tool loop) ⇄ [T] lexical_profile / rate_estimate    │
 │        ▼                                                                │
 │  [C2] Script Enrichment (Language Pack: readings/ruby/romanization/RTL) │
 │        ▼                                                                │
 │  [A4] Language QA Judge ×2 (Claude + other model family)                │
 │  [A5] Pedagogy & Safety Judge   [C3] Originality Gate (code+embeddings) │
 │        ▼                                                                │
 │  ██ HUMAN GATE 1: script approval (native reviewer per language) ██     │
 └─────────────────────────────────────────────────────────────────────────┘
                                 │
 ┌────────────────────── PRODUCTION ───────────────────────────────────────┐
 │  [A6] Voice Director ─▶ VoiceDirectives ─▶ [C4] TTS Workers (per line)  │
 │                                             └▶ [C5] Aligner + Mastering │
 │  [A7] Art Director ─▶ ShotList + ThumbnailSpec ─▶ [C6] Image Workers    │
 │              (Audience Profile: rig/pose cues ─▶ 2D rig library)        │
 │  [C14] Music & SFX picker (licensed library only, ducked under speech)  │
 │        ▼                                                                │
 │  [C7] Composer: build Remotion props ─▶ [C8] Render farm ─▶ master.mp4  │
 │        ▼                                                                │
 │  [A8] Visual QA (vision on sampled frames) + [C9] tech checks           │
 └─────────────────────────────────────────────────────────────────────────┘
                                 │
 ┌────────────────────── PACKAGING & RELEASE ──────────────────────────────┐
 │  [A9] Packager: title/desc/tags/chapters/thumbnail copy (multi-lang)    │
 │  [C12] Thumbnail renderer (≤3 variants) · [C13] Captions (SRT/VTT)      │
 │  [A10] Derivatives: Shorts cuts, PDF transcript, Anki deck, RSS audio   │
 │  [A11] Compliance Officer: MFK flag, synthetic disclosure, policy check │
 │  ██ HUMAN GATE 2: final watch + publish approval ██                     │
 │  [C10] Publisher: upload private ─▶ PublishReceipt ─▶ publishAt, RSS    │
 └─────────────────────────────────────────────────────────────────────────┘
                                 │
 ┌────────────────────── POST-PUBLISH ─────────────────────────────────────┐
 │  [C11] Analytics ─▶ [A12] Analyst (weekly) ─▶ proposals ─▶ human ─▶ cfg │
 │  Patch (metadata/captions/thumbnail) · Retire (unlist) · Supersede      │
 └─────────────────────────────────────────────────────────────────────────┘
```

Legend: `[A#]` = LLM agent · `[C#]` = deterministic code service · `[T]` = tool exposed to an agent · `██` = human gate.

---

## 3. Agent roster

| # | Agent | Runs | Pattern | Model (default → candidate after eval) | Input → Output |
|---|---|---|---|---|---|
| A1 | **Showrunner** | per season | single call, structured output, adaptive thinking, effort `high` | `claude-opus-5` | Resolved config (Pack + Level + Audience + Bible) + level syllabus + analytics summary → `SeasonPlan` (theme, arc, 10–12 episode loglines, target-word pool, grammar sequence) |
| A2 | **Scriptwriter** | per episode | single call, structured output, streaming | `claude-opus-5` → `claude-sonnet-5` | `EpisodeSpec` + Bible + few-shot → `Script` |
| A3 | **Level Editor** | per episode | **Tool Runner loop** (≤4 turns), tools `lexical_profile`, `rate_estimate`, `find_simpler_synonym` | `claude-opus-5` → `claude-sonnet-5` | `Script` + gate failures → patched `Script`, or escalate |
| A4 | **Language QA Judge** | per episode | 2 independent calls: Claude + another model family | `claude-opus-5` + Gemini 3.x Pro | `Script` → `QAReport{issues[line_id, severity, fix]}` |
| A5 | **Pedagogy & Safety Judge** | per episode | single call with a rubric | `claude-opus-5` | `Script` + spec + rubric → scores + hard-gate verdicts (age-appropriate safety from the Audience Profile, hook, arc, interaction) |
| A6 | **Voice Director** | per episode | single call | `claude-sonnet-5` | `Script` + voice map → `VoiceDirectives` (per-line style/emotion tags, pause ms, slow/natural variant, SSML hints, pronunciation overrides from the Language Pack: pitch accent, tones, stress) |
| A7 | **Art Director** | per episode | single call, optional Tool Runner for asset search | `claude-sonnet-5` | `Script` + Bible style + asset library → `ShotList` (segment → layout template, image prompt or reused asset id, character pose, on-screen text) **and `ThumbnailSpec`** (concept, character pose, text slot, up to 3 variants) |
| A8 | **Visual QA** | per render | vision call on about 12–20 sampled frames plus the subtitle track | `claude-opus-5` | frames + expected on-screen text → defects (overflow, wrong reading aids, broken RTL/shaping, missing glyphs, off-model character, unreadable contrast) |
| A9 | **Packager** | per episode | single call | `claude-sonnet-5` | `Script` + analytics of top titles → `PublishPackage` metadata in the target language plus each support language, chapters, thumbnail copy per variant and the default variant, pinned-comment text |
| A10 | **Derivatives** | per episode | single call | `claude-sonnet-5` → `claude-haiku-4-5` | `Script` + timings → Shorts cut list, Anki notes, PDF layout JSON |
| A11 | **Compliance Officer** | per episode | single call + code checks | `claude-opus-5` | `PublishPackage` + Bible + policy digest → pass/fail with reasons (MFK, synthetic label, clickbait/deceptive-educational, reused-content risk) |
| A12 | **Analyst** | weekly (scheduled) | agent with read-only analytics tools; candidate for a **Managed Agents scheduled deployment** | `claude-opus-5` | YouTube Analytics + QA history → tuning proposals (never auto-applied) |

**Model policy:**
- Default every station to `claude-opus-5` with adaptive thinking.
- Move a station down (Sonnet 5, Haiku 4.5) **only after its eval shows quality holds**. That is a deliberate business decision, not something to do by default.
- Use **effort** before switching models: `low` for Packager/Derivatives, `high` for Showrunner and the judges.
- **A4 always pairs Claude with a model from another vendor.** Different model families catch different errors.

**When to use which agent surface:**
- **Single structured-output calls** (`client.messages.parse` / `output_config.format`) cover about 80% of stations.
- **Tool Runner** (`client.beta.messages.tool_runner`) for A3 and optionally A7, where the model needs to call deterministic tools repeatedly.
- **Message Batches** (50% cheaper, asynchronous) for season-level bulk work: generating 12 scripts overnight, bulk QA and derivatives.
- **Managed Agents** only for A12 (scheduled, stateful, hosted), or later for an "ops copilot".
- The **Claude Agent SDK** isn't needed in the production path. Use it (or Claude Code) as a developer tool for building templates.

---

## 4. Artifacts and contracts

All artifacts are JSON, schema-versioned, and stored at `artifacts/{channel}/{season}/{episode}/{station}@{hash}.json`. The episode record points to the current version of each.

### 4.0 Configuration layers: how "any language, any age, any level" works

Every episode is produced from a **resolved configuration**: four layers merged in order, with later layers overriding earlier ones. Stations only ever see the resolved result. It is also the cached prompt prefix.

```
 Language Pack (what the language needs)      e.g. pack:ja, pack:en, pack:ko, pack:es, pack:ar
      +  Level Framework (what "level X" means)    e.g. cefr, jlpt→cefr, hsk3→cefr, yle, custom
      +  Audience Profile (who is watching)        e.g. toddler, early-reader, kid, teen, adult, senior, heritage
      +  Channel Bible (brand + variety)           e.g. "Haru's Japanese", "Slow English Café"
      ─────────────────────────────────────────
      =  ResolvedConfig  → every station
```

#### Language Pack (one per target language; code plug-in + data)
Each pack implements one interface and ships a conformance test suite. A new language is accepted only once its tests pass.

```python
class LanguagePack(Protocol):
    code: str                       # BCP-47, e.g. "ja", "zh-Hans", "ar", "pt-BR"
    script_direction: Literal["ltr", "rtl"]
    rate_unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    native_rate: float              # typical native rate in rate_unit (e.g. ja ≈ 7.8 mora/s, en ≈ 6.2 syl/s)
    def tokenize(self, text) -> list[Token]           # spaCy/Stanza/Sudachi/jieba/...
    def lemma_level(self, token, framework) -> Level | None   # from the pack's leveled wordlist
    def speech_units(self, text) -> int                # for measuring rate
    def reading_aids(self, text, policy) -> Ruby[]     # furigana / pinyin / romaja / harakat / none
    def romanize(self, text) -> str | None
    def pronunciation_hints(self, text) -> list[Hint]  # pitch accent, tones, stress, liaison
    def dictionary_gloss(self, lemma, support_lang) -> str | None
    fonts: list[str]                                   # glyph coverage for render + Visual QA
    voices: list[VoiceRef]                             # per TTS vendor, tagged by age/gender/style
    licenses: list[DataLicense]                        # wordlist/dictionary provenance for the Compliance Officer
```

| Pack example | Tokenizer | Reading aids | Rate unit | Wordlist backbone |
|---|---|---|---|---|
| `en` | spaCy | none (IPA optional) | wpm | NGSL + own CEFR mapping |
| `ja` | Sudachi / fugashi+UniDic | furigana by level, romaji toggle | mora/s | tanos + JMdict |
| `zh` | jieba / pkuseg | pinyin (tone marks) by level | syllables/s (1 per hanzi) | HSK 3.0 ⚠️ licence check, KELLY |
| `ko` | Kiwi | romaja at early levels | syllables/s (1 per block) | NIKL learner list (KOGL-1) |
| `ar` | Stanza / CAMeL | harakat by level, RTL | syllables/s | KELLY + frequency bands |
| any other | Stanza/UDPipe | ICU transliteration if non-Latin | syllables/s (pyphen) | FrequencyWords bands, calibrated by a reviewer |

#### Level Framework (maps any exam scale onto one internal scale)
- The internal scale is **CEFR Pre-A1 → C2**. Exam scales such as JLPT, HSK 3.0, TOPIK, ACTFL and Cambridge YLE are **aliases** mapped onto it. The mappings are approximate and stored with a confidence value.
- A pack's own leveled list overrides the generic CEFR tags when one exists (e.g. tanos for `ja`).
- Each level carries **pedagogical bands** that the gates use:
  - coverage target;
  - new-word budget;
  - sentence-length band;
  - **rate band as a fraction of the pack's `native_rate`** (e.g. A2 at 0.65–0.75), multiplied by the Audience Profile's multiplier (research.md §A.4);
  - pause lengths;
  - reading-aid policy;
  - politeness or register policy;
  - allowed grammar.

#### Audience Profile (one per age segment; independent of language)
| Profile | Ages | Key settings |
|---|---|---|
| `toddler` | 2–4 | Made-for-Kids = true, rate ×0.85, 2–4 min, shots ≥20 s, songs + TPR, pause 3–4 s, co-viewing prompts, no autoplay-bait |
| `early_reader` | 5–7 | MFK = true, 4–7 min, phonics/sight words, karaoke highlight, Q&A pauses |
| `kid` | 8–12 | MFK = true, 8–12 min, serialized stories, quizzes |
| `teen` | 13–17 | MFK = false, but YouTube's under-18 protections apply (AI age estimation; no personalized ads); no mature themes; school/exam and pop-culture topics |
| `adult` | 18+ | podcast/story/topic formats, 6–25 min |
| `senior` | 60+ | rate ×0.85–0.9, longer pauses, quiet music, boosted 1–4 kHz speech band, large high-contrast captions, one idea per screen, more repetition |
| `heritage` | any | speaks but can't read, or wants register/literacy work; reading-aid-heavy, less L1 scaffolding |

Each profile sets:
- the format whitelist;
- length and pacing;
- visual rules (font size, cut rate, character style);
- the safety rubric for A5;
- compliance flags for A11 (e.g. `made_for_kids`);
- how voices are picked.

#### Channel Bible (brand layer: one per published channel)
```yaml
channel: haru-japanese                 # example channel
target: {pack: ja, framework: jlpt, levels: [N5, N4, N3]}
audience: adult                        # a channel can also span profiles, e.g. [teen, adult]
support_languages: [en, vi]            # L1 support for glosses/metadata; set per audience market
persona: {name: "Haru", bio: "...", speaking_style: "...", catchphrases: [...]}
cast: [{id: haru, voice: {vendor: aivis, id: "..."}}, {id: mika, ...}]
formats: [slow_dialogue_explain_replay, serial_story, topic_talk, shadowing]   # subset of the profile whitelist
visual_theme: {palette, fonts, layout_templates: [podcast_a, podcast_b, story_scene, vocab_grid, quiz]}
variety_rules:                         # anti-"mass-produced" guardrails
  min_distinct_layouts_per_ep: 3
  max_same_format_in_a_row: 2
  rotate_openings: true
  max_embedding_similarity_to_last_20: 0.85
```

#### Format Library (shared across all layers)
- Formats are templates. Each one has a script schema variant, a Remotion composition and a QA rubric.
- Each format is tagged with the **age profiles and level ranges it suits**. Examples:
  - `song_tpr`: toddler/early_reader × Pre-A1–A1
  - `graded_story`: all profiles × A1–B2
  - `slow_dialogue_explain_replay`: teen/adult/senior × A1–B1
  - `topic_talk`: teen/adult × B1–C2
  - `shadowing`: adult/senior × any level
  - `news_digest`: adult × B1+
- The scheduler only picks formats that fall inside the resolved configuration.

### 4.2 Episode Spec (written by the scheduler; the work order)
```json
{"episode_id":"jp-N4-s02e05","channel":"jp-podcast","level":"N4","format":"slow_dialogue_explain_replay",
 "theme":"konbini","target_words":["温める","袋","お箸",...],"review_words":["いくら","ください",...],
 "grammar_point":"〜てもいいですか","rate_target":{"unit":"mora_s","min":4.5,"max":5.3},
 "length_min":[6,8],"season_arc_beat":"Mika's first part-time shift","cast":["haru","mika"],
 "source":"season","season_id":"jp-N4-s02","ordering":"strict","publish_slot":"2026-11-03T12:00:00+09:00",
 "config_hash":"sha256:…","budget_usd":3.0}
```

### 4.3 Script (written by A2 and patched by A3)
```json
{"episode_id":"...","title_working":"...","hook":"...",
 "segments":[{"id":"s1","type":"dialogue","speed":"slow","layout":"podcast_b",
   "lines":[{"id":"s1l1","speaker":"mika","text":"すみません、お箸をもらってもいいですか。",
             "translation":{"en":"...","vi":"..."},"pause_after_ms":1500,"visual_cue":"chopsticks"}]},
   {"id":"s2","type":"explanation","lines":[...]}, {"id":"s3","type":"quiz","items":[...]}],
 "vocab":[{"word":"お箸","gloss":{"en":"chopsticks","vi":"đũa"},"is_target":true}],
 "grammar_notes":[...],"interaction_prompts":[...]}
```
Reading aids (furigana, pinyin, romaja, transliteration, vowel marks) and romanization are **never** trusted from the LLM. C2 adds them in `script.enriched.json` using the Language Pack's deterministic engine.

`source` is `season` or `adhoc`. An ad-hoc spec is typed by the operator (theme, optional target words, optional format); C1 fills `review_words` from the exposure ledger and validates the format against the resolved configuration. `ordering: strict` means the episode may not publish before its predecessor (serial stories); `loose` lets the calendar reorder it.

*The Spec and Script above use the JP N4 example. An EN, Korean or kids episode fills the same schema, with the rate unit, reading aids and pacing coming from its layers.*

### 4.4 The remaining contracts
| Artifact | Written by | Key fields |
|---|---|---|
| `LevelReport` | C-profiler | coverage %, off-level tokens[], target-word counts, sentence-length stats, estimated rate |
| `QAReport` | A4, A5 | issues[{line_id, category, severity, suggested_fix}], rubric scores, hard_gate_failures[] |
| `VoiceDirectives` | A6 | per line: voice_id, style tags, rate, pause_ms, accent overrides, variant (slow/natural) |
| `AudioManifest` | C4, C5 | per line: wav uri, duration, word/char timestamps; master uri; LUFS |
| `ShotList` | A7 | per segment: template, assets[], image prompts, character pose/expression, on-screen text |
| `RenderProps` | C7 | Remotion input props (a deterministic function of Script + Audio + ShotList) |
| `PublishPackage` | A9, A11 | title/desc/tags per language, chapters, thumbnail spec, MFK flag, synthetic flag, playlist ids, publishAt |
| `SeasonPlan` | A1, edited by the operator | theme, arc, episode loglines[], target-word pool, grammar sequence, approved_by, approved_at |
| `ThumbnailSpec` / `ThumbnailSet` | A7 / C12 | concept and pose per variant; rendered PNGs (1280×720, ≤2 MB), legibility results, chosen variant |
| `CaptionSet` | C13 | SRT/VTT per language (target + support), cue rules used, sync report |
| `GateDecision` | console | gate (0/1/2), user, decision (approve / edit-and-approve / reject), diff, notes, timestamp |
| `CostLedger` | orchestrator | per station: vendor, units, USD; running total vs the episode budget |
| `PublishReceipt` | C10 | platform, external video id, upload timestamp, publishAt, status, quota units used |

### 4.5 Configuration pinning and versioning
- Every layer is versioned: Bibles, Audience Profiles and Level bands in Postgres with history; Language Packs by git tag.
- `ResolvedConfig` is computed once per episode when the spec is created and stored with its `config_hash`. All stations read the stored copy, never the live layers.
- Changing a layer creates a new version. Episodes already past `SPEC` keep theirs. The console shows "N in-flight episodes use an older Bible; re-resolve?" and re-resolving restarts the episode from `DRAFTED`.
- Artifact schemas follow semver. A station accepts any minor version within its major; migrations are code, not prompts.
- Each station has a `station_version` (prompt hash + model id + code version). It is part of the artifact hash (principle 5), so a prompt change never silently reuses a cached output and a rollback restores the old cache.

---

## 5. Season and episode state machines

```
SEASON:  PLAN_DRAFTED ─▶ ◆PLAN_APPROVED ─▶ SPECS_EMITTED ─▶ IN_PRODUCTION ─▶ COMPLETE
                 ▲ reject/edit ─┘                                  (all episodes published or cancelled)

EPISODE:
 SPEC ─▶ DRAFTED ─▶ LEVEL_OK ─▶ ENRICHED ─▶ QA_OK ─▶ ◆SCRIPT_APPROVED
                     ▲   │ fail (≤4 edit loops)       │ reject → back to DRAFTED with reviewer notes
                     └───┘ then ESCALATED             ▼
 ◆SCRIPT_APPROVED ─▶ VOICED ─▶ VISUALS_READY ─▶ RENDERED ─▶ VISUAL_QA_OK ─▶ PACKAGED
                        ▲ re-voice single lines            │ defects → re-render only
                        └──────────────────────────────────┘ the affected segments
 PACKAGED ─▶ COMPLIANT ─▶ ◆FINAL_APPROVED ─▶ UPLOADED ─▶ SCHEDULED ─▶ PUBLISHED ─▶ ANALYZED(+7d, +28d)
                                                  (receipt stored)   (publishAt set)
 PUBLISHED ─▶ PATCHING ─▶ PUBLISHED        metadata, captions, thumbnail, pinned comment only (§11)
 PUBLISHED ─▶ RETIRED                      unlisted or private; optional `superseded_by` → new episode
 any state ─▶ ESCALATED (human queue) · BUDGET_EXCEEDED · CANCELLED
 lane      ─▶ PAUSED (no new jobs dispatched; in-flight jobs finish; nothing publishes)
```
◆ = human gate (0, 1, 2).

- Each transition is a job in the queue. Retries use backoff, capped per station. Every job writes to the `CostLedger`.
- A per-episode **cost budget** (default $3, set per channel) and a **loop budget** stop runaway rewrite loops.
- Human edits at the gates are saved as diffs in `GateDecision`. They become few-shot examples and eval data.
- **`UPLOADED` is separate from `SCHEDULED`** so a crash between the two never uploads twice: C10 first uploads as private and stores the `PublishReceipt` with the video id, then sets `publishAt`, thumbnail, captions and playlist in later idempotent steps keyed by that id.
- **Ordering.** `ordering: strict` episodes publish in sequence. A rejected or escalated episode holds its slot; C16 shifts later slots and notifies the operator. The exposure ledger is updated only on `PUBLISHED`, so C1 recomputes review words for later episodes if the order actually changes.
- **Re-run from any station.** The console can reset an episode to any earlier state. Content addressing makes the untouched stations free.
- **Gate 1 pre-render preview** uses cached TTS per line with the final voices; the cost is small because the same lines are reused in `VOICED` if the reviewer does not change them.

---

## 6. Quality system: gates by station

| Gate | Type | Pass criterion (from research.md §2–3) |
|---|---|---|
| Lexical coverage | code ⛔ | ≥95% of tokens at or below the level, ≥98% for on-screen text; new words ≤ spec; each target word ≥5× |
| Rate and length | code ⛔ | estimated rate (in the pack's `rate_unit`) within ±10% of the band for the level and audience; duration within the spec length |
| Reading aids | code ⛔ | every token that needs an aid under the level policy has one from the pack's engine (kanji→furigana, hanzi→pinyin, …); ambiguous readings are flagged |
| Language QA | LLM ×2 | no `critical` issue from either judge; `major` issues get patched and re-judged once |
| Pedagogy | LLM | rubric ≥4/5 on hook, clarity, interaction; hard gates from the Audience Profile's safety rubric |
| Originality | code ⛔ | embedding similarity to the last 20 episodes ≤0.85; layout/format rotation rules met |
| Audio tech | code ⛔ | −14 LUFS ±1, no clipping, pauses within spec, timestamps cover 100% of subtitle tokens |
| Visual QA | LLM vision + code | no text overflow; reading aids aligned; RTL/shaping correct; every glyph covered by the pack fonts; character on-model; contrast ≥ WCAG AA; text size at or above the Audience minimum |
| Compliance | LLM + code ⛔ | MFK flag correct; synthetic flag where required; metadata not misleading; wordlist/voice licence register satisfied |
| Season plan (Gate 0) | human ⛔ | the operator approves theme, arc and loglines; C1 runs only after approval |
| Thumbnail | code + LLM vision | text legible when downscaled to 168 px wide (YouTube sidebar size); ≤4 words unless the Audience Profile says fewer; contrast ≥ AA; character on-model; no claim A11 would call misleading |
| Captions | code ⛔ | every cue within ±150 ms of the audio; cue length and lines per cue from the pack (e.g. `ja` ≤16 chars, `en` ≤42 chars, 2 lines); 100% of script lines covered in every language |
| Publish idempotency | code ⛔ | no upload if a `PublishReceipt` exists for the episode; `publishAt` set only after the receipt is stored; a Shorts upload is its own receipt |
| Human 0 / 1 / 2 | human ⛔ | approve, or edit and approve, or reject with notes; every decision is a `GateDecision` row |

**Evals per agent:**
- Keep a golden set of about 30 episode specs per **pack × audience** pair in use, with approved outputs.
- Each Language Pack also has conformance tests: tokenization, levels, reading aids, rate measurement, and a TTS voice smoke test.
- Every prompt or model change to a station runs its eval before rollout.
- Track pass rate at each gate, human-edit distance, and cost per *approved* episode.

---

## 7. Production workers (deterministic)

| Service | Implementation | Notes |
|---|---|---|
| C1 Curriculum Scheduler | Python + Postgres | Picks the next target words in frequency order from the pack's leveled list; review slots at +1/+3/+7 episodes; updates the exposure ledger on publish |
| C2 Script Enrichment | Delegates to `LanguagePack.reading_aids / romanize / pronunciation_hints` | Adds ruby spans, romanization and pronunciation hints following the level's display policy; flags ambiguous readings for the judge and the human. Examples: `ja` uses fugashi+UniDic, JMdict, cutlet, pyopenjtalk (flags cases like 今日); `zh` would use a pinyin engine with tone marks; `ar` would add optional harakat |
| Profiler tools | `LanguagePack.tokenize / lemma_level / speech_units` | Exposed to A3 as `lexical_profile(text, level)`, `rate_estimate(lines)`, `find_simpler_synonym(word, level)` |
| C4 TTS Workers | adapter: Azure / Gemini / ElevenLabs / AivisSpeech / Style-Bert-VITS2 | One job per line, cached by (text, voice, directives); slow variants re-synthesized, never time-stretched |
| C5 Aligner + Mastering | TTS timestamps, falling back to WhisperX; FFmpeg `loudnorm` | Assembles lines and pauses; writes the AudioManifest |
| C6 Image Workers | adapter: Imagen / Flux Kontext / Flux LoRA | Checks the **asset library** first so assets get reused; kids characters come from rigs, not regeneration |
| C7 Composer | TS function: artifacts → Remotion props | Pure and deterministic, so it's unit-testable |
| C8 Render farm | Remotion (local or Lambda) + FFmpeg encode | Renders per segment and concatenates, so a partial re-render is cheap |
| C9 Tech checks | ffprobe, subtitle validators | Resolution, duration, audio sync |
| C10 Publisher | YouTube Data API v3 | Private upload + `publishAt`, thumbnail, playlist, captions (400 units each, so budget the daily quota), `selfDeclaredMadeForKids`, `containsSyntheticMedia`; RSS feed for Spotify/Apple |
| C11 Analytics | YouTube Analytics API → warehouse | Retention per segment is mapped back to script segment ids and config layers, so the Analyst can say "explanation segments at A2/N4 lose 30%" or "senior viewers finish slow-rate episodes more often" |
| C12 Thumbnail renderer | Remotion still composition + sharp | Renders ≤3 variants from `ThumbnailSpec` + Packager copy; 1280×720, ≤2 MB; legibility check by downscaling to 168 px and running OCR; the chosen variant is uploaded, and the others go to YouTube's Test & Compare when the channel has it |
| C13 Captions | from `AudioManifest` timestamps | SRT/VTT for the target language and each support language (translations come from the Script); cue segmentation rules per pack; the same cues feed the burned-in subtitle track in C7 so the two never diverge |
| C14 Music & SFX | licensed library + FFmpeg `sidechaincompress` | Picks by the Bible's mood tags; records a `license_id` per asset on the episode; ducks under speech; no generated music until its terms are verified (research.md on Suno) |
| C15 Notifier | email / Slack / Telegram adapter | Gate queues, escalations, budget breaches, publish confirmations and failures, slot shifts; idempotent per (episode, event); daily digest or instant per role |
| C16 Publish calendar | Postgres | Slots per channel from cadence and time zone; keeps `strict` order; a rejected episode holds its slot and later slots shift; prevents two lanes publishing on the same channel within the same hour; exposes the calendar view to the console |

---

## 8. Context and cost engineering

- **Prompt caching layout.** The prefix is ordered from stable to volatile:
  1. tools;
  2. the system prompt (station instructions);
  3. the ResolvedConfig (Pack summary + Level bands + Audience Profile + Channel Bible);
  4. level wordlist and grammar excerpt (only the relevant level);
  5. few-shot examples;
  6. `cache_control` breakpoint;
  7. then the volatile `EpisodeSpec` / `Script`.

  Never put timestamps or run ids in the prefix. Verify with `usage.cache_read_input_tokens`.
- **Batch API** for anything not needed within the hour: season script drafts, overnight QA sweeps, derivatives. It is 50% cheaper.
- **Token budget per episode (estimate):** A2 about 15K in / 6K out; A3 2–4 turns; each judge about 10K / 2K; the others are small. That totals roughly 80–120K tokens per episode.
  - All-Opus 5 ($5/$25 per M) costs about **$0.70–1.20 per episode** before caching, and less with caching and batch.
  - TTS, images and render add about $0.30–1.50 (see research.md §4.1).
- **Budget guards:** a cost ceiling per episode and per day, enforced by the orchestrator. Exceeding it sends the job to `BUDGET_EXCEEDED` for human triage.

---

## 9. Human-in-the-loop console

A small web app (Next.js or similar) on top of the orchestrator's API. It is the only surface the operator and reviewers see.

**Screens**
- **Queue:** items waiting at Gate 0, Gate 1, Gate 2 or `ESCALATED`, sorted by publish slot; filtered to the channels and packs the user is assigned to. A reviewer sees only Gate 1 items for their pack.
- **Season plan (Gate 0):** theme, arc, loglines as editable cards, the target-word pool, and a preview of the publish calendar. Approve emits the specs.
- **Ad-hoc episode form:** theme, optional target words, format from the allowed list, optional slot. Creates a spec with `source: adhoc`.
- **Script review (Gate 1):** line-by-line, with the pack's reading aids, RTL-aware; judge issues shown inline with suggested fixes; audio preview per line with the final voice; edit a line to re-run only the affected downstream stations; reject with notes.
- **Final review (Gate 2):** video player; the rendered thumbnails side by side at full size and at 168 px; title and description shown as a YouTube card preview in each language; captions toggle; compliance checklist with each flag's reason; publish slot picker; the Shorts and derivatives list; a publish button.
- **Episode page:** state timeline with timestamps, cost per station vs budget, every artifact with its hash, "re-run from station X", cancel, and after publish the patch and retire actions (§11).
- **Calendar:** slots per channel, drag to move `loose` episodes, locked `strict` runs.
- **Config editor:** Channel Bibles, Audience Profiles and Level bands with version history and a diff view; shows how many in-flight episodes would be affected. Language Packs are code and change through pull requests.
- **Reviewer roster and assignment:** native reviewers per pack with capacity per week; Gate 1 items route round-robin within a pack, with manual reassignment and an SLA.
- **Dashboards:** gate pass rates, cost per approved episode, time in queue per gate, reviewer SLA, retention by level and segment type, Analyst proposals with accept and dismiss.
- **Lane controls:** pause and resume a channel; pause all publishing; an environment banner (dev, staging, prod).

**Notifications (C15)**
- Reviewer: new Gate 1 item (instant or daily digest), SLA warning at 24 h.
- Operator: Gate 0 and Gate 2 items, escalations, budget breaches, upload failures, slot shifts, publish confirmations.
- Admin: quota near limit, OAuth refresh failure, vendor errors above threshold.

**Target reviewer time:** at most 15 minutes per podcast episode and at most 25 minutes per kids episode. **Target operator time:** at most 25 minutes per episode across Gate 0 share and Gate 2.

---

## 10. Data model (Postgres)

| Table | Key columns | Notes |
|---|---|---|
| `workspace`, `user`, `role_binding` | user, channel, role | roles from §1.5; a binding without a channel is workspace-wide |
| `channel` | id, bible_version, pack, framework, audience, youtube_channel_id, cadence, timezone, budget_usd, paused | one lane |
| `config_version` | layer, id, version, body, created_by | history for Bibles, Profiles, Level bands |
| `season` | id, channel, plan artifact, status, approved_by | |
| `episode` | id, channel, season (nullable), source, status, config_hash, ordering, publish_slot, budget_usd, supersedes, superseded_by | the state machine row |
| `artifact` | episode, station, station_version, hash, uri, schema_version | content-addressed |
| `job` | episode, station, attempt, status, started/finished, error | queue history |
| `gate_decision` | episode or season, gate, user, decision, diff, notes, ts | audit trail and training data |
| `exposure_ledger` | channel, lemma, episode, published_at | updated only on publish |
| `asset` | id, type (image, rig, music, sfx, font), uri, license_id, provenance | the library C6 and C14 search first |
| `license` | id, source, terms_url, commercial_ok, attribution, expires | read by A11 |
| `cost_ledger` | episode, station, vendor, units, usd, ts | |
| `publish_receipt` | episode, platform, external_id, upload_ts, publish_at, status, quota_units | idempotency key for C10 |
| `analytics_snapshot` | episode, day, metrics json | C11 output |
| `notification` | episode, event, recipient, sent_at | idempotency key for C15 |

Artifacts themselves live in the content-addressed store (local disk in dev, S3 in prod); Postgres holds pointers and state.

---

## 11. Post-publish lifecycle

YouTube does not allow replacing a video's media, so the factory distinguishes what can be patched from what needs a new video.

| Situation | Action | State |
|---|---|---|
| Typo in title, description, tags, chapters, localization | operator edits in the console; C10 `videos.update` | `PATCHING` → `PUBLISHED` |
| Wrong or missing caption line | fix the line in the Script; C13 regenerates; C10 replaces the caption track | `PATCHING` → `PUBLISHED` |
| Weak thumbnail | pick another rendered variant or re-run C12 with a new spec; `thumbnails.set` | `PATCHING` → `PUBLISHED` |
| Minor content error (one line mispronounced, small factual slip) | errata in the pinned comment plus a caption fix; logged on the episode | `PATCHING` → `PUBLISHED` |
| Major content error, wrong level, policy problem | set to unlisted (not deleted, to keep history), re-run from the needed station, upload as a **new episode** with `supersedes`; the old video gets a card and end screen pointing to the new one | `RETIRED` + new episode |
| Copyright claim or policy strike notification | episode moves to `ESCALATED`, operator and admin notified, the asset's `license` row flagged, C14 and C6 stop using the asset | `ESCALATED` |
| Analytics show a segment type underperforming | A12 proposal; operator edits Level bands or the Bible; applies to future episodes only | no change to published episodes |

Comments: Made-for-Kids channels have comments disabled by YouTube; other channels default to holding comments for review in v1, and moderation is out of scope (§18).

---

## 12. Operations

**Secrets and accounts**
- One YouTube OAuth refresh token per channel, stored in a secret store, never in config files or artifacts. A failed refresh pauses the lane and notifies the admin.
- Vendor keys (LLM, TTS, image) are per environment; prod keys are never used in dev or staging.

**YouTube Data API quota** (default 10,000 units per project per day)

| Call | Units | Per episode |
|---|---|---|
| `videos.insert` | 1,600 | 1 (plus 1,600 per Short) |
| `captions.insert` | 400 | 1 per language |
| `thumbnails.set` | 50 | 1 |
| `videos.update`, `playlistItems.insert` | 50 each | 1–3 |

An episode with two caption languages costs about 2,500 units, so a single project publishes at most 3–4 episodes a day with no Shorts. C16 budgets quota per lane, Shorts are scheduled on separate days when quota is tight, and the admin requests a quota increase before Phase 4 scale.

**Vendor limits and fallbacks**
- Each adapter has a concurrency limit, a circuit breaker and a retry policy.
- TTS voices are pinned per cast member. There is **no automatic voice fallback**, since a voice change breaks the persona; a vendor outage pauses `VOICED` for that lane and notifies the operator.
- LLM fallback is allowed within the same family (e.g. Opus 5 to Sonnet 5) only for non-judge stations and is recorded in the `CostLedger`.

**Observability**
- One trace id per episode; each station is a span with inputs' hashes, output hash, tokens, cost and duration.
- LLM requests and responses are logged with the artifact hash for one year, so any output can be replayed and diffed.
- Dashboards: gate pass rate per station, cost per approved episode, time in queue per gate, reviewer SLA, vendor error rate, quota use, cache hit rate (`usage.cache_read_input_tokens`).

**Runbook (automatic action, then human action)**

| Failure | Automatic | Human |
|---|---|---|
| Station fails after retries | `ESCALATED`, notify operator | re-run, edit input, or cancel |
| Budget exceeded | `BUDGET_EXCEEDED`, notify | raise budget for this episode or cancel |
| Vendor outage | circuit open, lane jobs for that station wait, notify admin | wait or switch adapter in config |
| Quota exhausted | C10 defers to next day, slots shift, notify | approve shifted calendar |
| OAuth refresh fails | lane `PAUSED`, notify admin | re-authorize in console |
| Render farm backlog | queue by publish slot, notify if a slot is at risk | add workers or move slots |
| Policy strike | episode `ESCALATED`, publishing paused for the channel | review, patch or retire |

**Kill switches:** pause a lane; pause all publishing; freeze station versions (no prompt or model changes roll out).

**Environments**
- `dev`: fixture Language Pack `xx-fixture` and fake vendor adapters; the whole pipeline runs in CI in under 10 minutes and produces a placeholder MP4.
- `staging`: real vendors, a private staging YouTube channel, weekly end-to-end run.
- `prod`: real channels. Promotion of a station version requires its eval to pass in staging.

**Retention:** per-line TTS cache 90 days; masters and approved artifacts kept indefinitely; LLM logs one year; no viewer PII is stored, only reviewer and operator accounts.

---

## 13. Licensing and provenance register

Every input that ends up in a video has a `license` row, and A11 fails an episode whose assets are not covered.

| Asset class | Source of truth | Rule |
|---|---|---|
| Wordlists and dictionaries | Language Pack `licenses` | only commercially licensed lists (NGSL, tanos, JMdict, NIKL, KELLY); EVP, Oxford and CEFR-J are blocked |
| TTS voices | vendor terms per voice | commercial use allowed; synthetic-media disclosure set when the vendor or YouTube requires it; voice clones of real people only with written consent on file |
| Music and SFX | library license per track | Content ID safe; attribution text auto-added to the description when required |
| Fonts | font license per family | OFL or commercial licence covering video and thumbnails; the Pack's font list is checked at render |
| Generated images | image vendor terms | no real-person likeness, no third-party IP; prompts are stored with the asset |
| Few-shot examples and golden sets | own work | approved scripts only, never scraped material |

The register is also the input for the "reused content" check: A11 flags an episode whose asset reuse ratio exceeds the Bible's variety rules.


---

## 14. Scaling: new languages, ages and levels, and channels as lanes

**Adding coverage is configuration, not new agents:**

| To add… | You write | Effort [P] |
|---|---|---|
| A new **level** in an existing language | Level bands, plus the syllabus slice | hours |
| A new **audience** (e.g. seniors) | An Audience Profile (pacing, visuals, safety rubric, format whitelist) and golden evals | days |
| A new **support language** (e.g. Indonesian explanations) | A `support_languages` entry, glossary QA and metadata locales | hours to days |
| A new **target language** | A Language Pack (tokenizer, leveled list, reading aids, rate unit, fonts, voices, licences) that passes conformance tests, plus a native reviewer | 1–3 weeks per language, depending on script and NLP maturity |
| A new **channel** | A Channel Bible (persona, cast, theme, variety rules) that points at existing layers | days |

**Channel strategy is a business choice the factory doesn't care about.** Any of these work:
- one channel per target language × audience, with levels as playlists (recommended default);
- one channel per language that spans audiences;
- a global "hub" channel with multi-language audio.

The Channel Bible just declares which slice it publishes.

**Operations:**
- **Lanes:** each channel is a lane with its own quota share. Stations are shared code, parameterized by the ResolvedConfig.
- **Concurrency:**
  - The LLM stations scale out.
  - TTS and render are the heavy workers, sized by GPU and CPU.
  - YouTube publishing is serialized per channel under the quota budget: about 10K units a day, and captions dominate it.
- **Throughput target:**
  - Phase 3: about 15 episodes a week across lanes.
  - Later: 40+ episodes a week, limited by native-reviewer capacity per language, not compute.

---

## 15. Suggested repository layout

```
yt-channels/
├── config/
│   ├── frameworks/         # level frameworks + exam-scale→CEFR alias maps
│   ├── audiences/          # audience profiles (toddler … senior, heritage)
│   ├── formats/            # format library metadata (age × level tags, rubric refs)
│   └── channels/           # channel bibles (YAML), versioned
├── packs/                  # one Language Pack per target language (code + data + conformance tests)
│   ├── en/  ja/  …
│   └── xx-fixture/         # tiny synthetic pack + fake vendors for CI end-to-end
├── curriculum/             # syllabus themes, exposure ledger migrations
├── factory/                # Python
│   ├── orchestrator/       # state machine, queue workers, budgets
│   ├── agents/             # one module per A#: prompt, schema, eval
│   ├── tools/              # profiler, rate estimator, enrichment (delegate to packs)
│   ├── adapters/           # llm/, tts/, image/, music/, publish/, notify/
│   └── contracts/          # pydantic models = JSON schemas for artifacts
├── studio/                 # TypeScript: Remotion compositions + composer
├── console/                # human review web app
├── evals/                  # golden specs + approved outputs per pack × audience × station
├── ops/                    # runbooks, dashboards, alert rules, quota budgets
└── artifacts/              # local artifact store (S3 in prod)
```

---

## 16. Testing and definition of done

**Test layers**
- **Unit:** Language Packs (tokenize, levels, reading aids, rate), the Composer (pure function), C12 and C13 (deterministic output for the same inputs).
- **Contract:** every artifact validated at every station boundary; a schema change without a version bump fails CI.
- **Pack conformance:** the suite every new pack must pass (tokenization, levels, reading aids, rate measurement, fonts cover the wordlist, a TTS smoke test per voice).
- **Golden evals:** about 30 specs per pack × audience in use, with approved outputs; every prompt or model change runs its station's eval and must not regress pass rate or human-edit distance.
- **End-to-end in CI:** `xx-fixture` pack plus fake vendors, from `SPEC` to `SCHEDULED` against a fake publisher, under 10 minutes.
- **End-to-end weekly in staging:** real vendors, real upload to the private staging channel, then automatic retire.
- **Replay:** any published episode can be re-run from any station with pinned `station_version`s and produce byte-identical deterministic artifacts (C2, C7, C12, C13) and schema-valid LLM artifacts.

**Definition of done per build step** (used in §17): the step's tests above pass; its console screens exist if it has a gate; its runbook rows exist; cost per episode is measured; and the walkthrough in §1.5 can be performed for the steps built so far.

---

## 17. Build order

The first pilots use the three worked examples, chosen because together they exercise every layer:
- `en` is a Latin-script language with no reading aids;
- `ja` needs reading aids and a mora-based rate;
- the kids profile brings Made-for-Kids and strict safety rules.

| Step | Build | Proves |
|---|---|---|
| 0 | **Walking skeleton:** contracts, orchestrator state machine, artifact store, `xx-fixture` pack, fake adapters, CI end-to-end producing a placeholder MP4 | The assembly line works before any station is good |
| 1 | Contracts, **LanguagePack interface + conformance tests**, Level Framework (CEFR internal scale plus alias maps), Audience Profile schema, C1, A2, profiler, A3 loop | Level-correct scripts from any ResolvedConfig; pilot packs `en` and `ja` |
| 2 | C2 enrichment, A4, A5, originality gate, CLI review | Scripts that pass QA; first 10+10 human-approved scripts |
| 3 | A6, C4/C5, one Remotion podcast composition (RTL- and ruby-capable), C8 | An end-to-end MP4 |
| 4 | Console with Gate 0/1/2, reviewer routing and notifications (C15), publish calendar (C16), C10 with receipts, C12 thumbnails, C13 captions, A9/A11, staging channel | Scheduled publishing; the first adult lanes go live |
| 5 | A7 + asset library, A8, A10; a **third pack** in a new script family (e.g. `ko` or `zh`, or `ar` for RTL) | That "new language = new pack" holds in practice |
| 6 | C11 + A12, Batch API | Feedback loop per layer; lower cost |
| 6b | Post-publish lifecycle (patch, retire, supersede), C14 music library, licensing register UI | Safe operation at scale |
| 7 | Young-audience profiles (toddler, early_reader, kid): rig library, songs pipeline, stricter A5/A11. Then teen and senior profiles | The age axis works in both directions |

---

## 18. Non-goals for v1

- No live human host on camera; a real host voice is an open decision (§19), video is not.
- No live streams, premieres or community posts.
- No comment moderation beyond holding comments for review.
- No multi-audio-track videos; support languages appear as captions and metadata only.
- No automatic application of Analyst proposals.
- No automatic TTS voice fallback.
- No mobile console; the web console must work on a tablet for Gate 1.
- No paid course, app or membership integration.
- No automatic reuse of a published episode's footage in another episode.

---

## 19. Decisions still open (carried from research.md §7)
- Which slices to launch first. Use the scoring model in research.md §A.6.
- The support languages to offer.
- Whether to use a real host voice.
- Where the native reviewers per language come from.
- The business model.
- Notification channel for reviewers (email vs Slack vs Telegram).
- Thumbnail style per channel: host face, illustrated character, or text-first; and whether to use YouTube's Test & Compare.
- Whether Shorts publish to the main channel or a separate one (quota and audience implications).
- Reviewer SLA and compensation model, which sets the throughput ceiling.

All of these are values in the configuration layers or the gate settings. None of them changes the factory design.
