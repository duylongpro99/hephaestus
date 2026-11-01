# Language-Learning Video Platform: Research & Direction

**Goal:** a platform that self-produces language-learning videos for **any target language, any age, any level**, published across a family of YouTube channels.

**About the three examples.** English podcast (adults, CEFR A1–C1), Children's English (ages 2–12) and Japanese podcast (JLPT N5–N1) are **reference examples**. They cover three different kinds of case:
- a widely spoken language with a Latin script;
- a young audience with strict platform rules;
- a non-Latin script that needs reading aids.

They are not the product scope. The platform is built so each new language, age group or level is **configuration, not new code** (see §A). §1–§4 keep the detailed findings for the three examples, because a new language or audience will follow the same pattern.

Researched 2026-09-28, generalized 2026-09-29. Tags: **[E]** = sourced evidence, **[P]** = heuristic or estimate (tune it).
Prices and policies change fast. Re-check any vendor page before committing.

---

## 0. TL;DR: the recommended direction

0. **Generalize along three independent axes: target language × learner profile (age band + support language) × level.**
   - Each axis is a pluggable module: a **Language Pack**, an **Audience Profile** and a **Level Framework** that maps to CEFR as the common scale.
   - Formats come from a shared **Format Library**, tagged with the ages and levels each format suits.
   - A "channel" is just a published slice of that space.
   - Details in §A.
1. **Build a curriculum engine first and a video factory second.** YouTube's July 2025 "inauthentic content" policy and its 2026 AI-slop enforcement wave demonetize *templated, mass-produced* AI video. Protection comes from real pedagogy:
   - leveled scripts,
   - spiral vocabulary across episodes,
   - recurring characters or hosts,
   - visible human review,
   - on-screen teaching value.

   The platform's differentiator is the **lesson-spec → script → QA** pipeline. Rendering comes after that.
2. **Launch order.** Choose which slices to launch first with the scoring model in §A.6. It scores demand, competition, RPM, policy risk, how hard the language is to produce, and whether you have a reviewer. Applied to the three examples, it gives:
   1. **Japanese podcast (N5–N3 first, then N3–N2).** Intermediate CI (comprehensible input) is underserved and RPM is mid-range. Explanations in Vietnamese are also an option: Vietnam has about 165K Japanese learners, 6th in the world.
   2. **English podcast (A2–B1 first).** Demand is huge and education RPM is high (median about $10 for Western audiences). Most "slow English" channels are generic and unleveled, so rigorous A1–C1 leveling plus PDFs is a real differentiator.
   3. **Children's English last, and only as a premium product.** It has the lowest RPM ($1–3), the most AI-policy risk (200+ organisations asked YouTube to ban AI from Kids in April 2026), and COPPA liability. Start it only once you have original characters and songs, and plan revenue outside AdSense.
3. **Stack:**
   - Claude Sonnet 5 writes structured JSON scripts. A cross-model checker (Gemini or Opus) reviews them, and code-based lexical profilers enforce the level.
   - TTS is per line: Azure or Gemini for bulk, ElevenLabs for premium, and Style-Bert-VITS2/AivisSpeech for Japanese pitch-accent control.
   - Remotion templates assemble the video; FFmpeg handles loudness and encoding.
   - YouTube Data API v3 handles scheduled uploads.
4. **Unit cost is not the problem:** about **$0.50–1.80 per episode** on a budget stack and about $2–5 on a premium one. Human review time and channel differentiation are the real costs.
5. **Timing:** YPP (YouTube Partner Program) thresholds rise on **2027-02-01** (8,000 watch hours in 12 months). Long-form podcasts build watch hours quickly, so launch the podcast channels now and aim to apply before February.

---

## A. The general model: any language × any age × any level

The platform's unit of production is a point in a three-axis space:

```
            Target language (L2)          en, es, fr, ja, de, ko, it, zh, pt, hi, ar, vi, …
   ×  Learner profile                     age band (toddler … senior, heritage) + support language (L1)
   ×  Proficiency level                   CEFR Pre-A1 … C2 (exam scales mapped onto it)
   ×  Format (constrained by the other three)
   =  an EpisodeSpec
```

A **channel** is a published slice of this space, e.g. "Japanese × adult × N5–N3 × VI support". What is universal and what varies:

| Universal: build once | Varies per language: Language Pack | Varies per age: Audience Profile |
|---|---|---|
| Curriculum engine, spiral scheduler, exposure ledger | Tokenizer, lemmatizer, syllable/mora counter | Length, pacing, cut rate, font size |
| Coverage/repetition rules (95% coverage, 5–8 uses per target word, +1/+3/+7 recycling) | Leveled wordlist, dictionary, licences | Format whitelist (songs vs podcasts) |
| QA pipeline, originality gate, human gates | Reading aids (furigana, pinyin, romaja, harakat), romanization | Safety rubric, Made-for-Kids, teen protections |
| Render templates, publishing, analytics | Rate unit and native syllable rate; pronunciation hints (tone, pitch accent, stress) | Voice choice (child/adult/senior-friendly clarity) |
| Format Library | Fonts and glyph coverage; LTR/RTL; TTS voice roster and quality tier | Interaction style (TPR, Q&A pauses, quizzes) |

### A.1 One internal level scale: CEFR, with exam aliases [E]
Use **CEFR Pre-A1 → C2** as the internal scale, with sub-levels such as A1.1 and A1.2. Map every exam scale onto it as a **range with a confidence value**, never as a hard equivalence.

| Framework | → CEFR (approximate) | Confidence |
|---|---|---|
| DELF/DALF, DELE, Goethe | Native CEFR (A1–C2) | High (ALTE-audited) |
| Cambridge YLE | Starters = Pre-A1, Movers = Pre-A1/A1, Flyers = A1/A2 | High (official) |
| JLPT | N5≈A1, N4≈A2, N3≈A2/B1, N2≈B1/B2, N1≈B2/C1; no C2; score-dependent | Medium: official "for reference", receptive skills only. https://www.jlpt.jp/e/about/cefr_reference.html |
| HSK 3.0 (1–9) | 1–3 ≈ A1–A2, 4–6 ≈ B1–B2, 7–9 ≈ C1–C2 | Low: no official table; the old HSK 6 = C2 claim was rejected (the Fachverband Chinesisch put it at about B2) |
| TOPIK 1–6 | ≈ A1–C2 (some say A2–C1) | Low: no published standard-setting study |
| ACTFL | NL/NM <A1–A1 … AH≈C1, Superior≈C1–C2 | Low: ACTFL says ratings convert test by test only |

**Descriptor sources:**
- The CEFR Companion Volume (2020) adds Pre-A1 and mediation descriptors. https://rm.coe.int/cefr-companion-volume-with-new-descriptors-2018/1680787989
- The Council of Europe's **young-learner descriptor banks** cover ages **7–10 and 11–15** (Goodier & Szabo 2018). https://www.coe.int/en/web/common-european-framework-reference-languages/bank-of-supplementary-descriptors
- These give "can-do" goals per level *and* age that an LLM can plan from.

The channel shows the learner's familiar exam label (N4, HSK 3), while the factory runs on CEFR bands.

### A.2 Leveled vocabulary for any language [E]
Levels are resolved per language, using the best source available:
1. an **official or open leveled list**;
2. a **CEFR-tagged multilingual list**;
3. **frequency bands** as a proxy. For example, the top ~500 lemmas ≈ A1 and the top ~1,000 ≈ A2 [P]. Calibrate each band with a native reviewer.

| Resource | Languages | Levels? | License |
|---|---|---|---|
| **KELLY lists** | sv, en, no, el, it, pl, ar, zh, ru | **CEFR A1–C2** | CC BY-SA ✅ https://spraakbanken.gu.se/en/projects/kelly |
| **hermitdave FrequencyWords** (OpenSubtitles) | ~60 | frequency | CC BY-SA 3.0 ✅ (ShareAlike on derived lists) https://github.com/hermitdave/FrequencyWords |
| **Wiktionary via kaikki.org** | 4,000+ | no (POS, IPA, inflections, translations) | CC BY-SA + GFDL ✅ https://kaikki.org |
| wordfreq | ~40 | frequency | CC BY-SA 4.0 (frozen since 2024) |
| SUBTLEX family | ~10+ | frequency | varies, some research-only ⚠️ |
| Leipzig Corpora | 250+ | frequency | "freely available", terms unverified ⚠️ |
| Universal Dependencies | 150+ | no (grammar) | per treebank; **some are NC** ⚠️ |
| NGSL (en) | en | frequency bands | CC BY-SA ✅ |
| Tanos (ja) + JMdict | ja | JLPT (unofficial) | CC BY / CC BY-SA ✅ |
| NIKL learner vocab (ko) | ko | A/B/C bands | **KOGL Type 1** ✅ commercial use with attribution |
| HSK 3.0 list (zh) | zh | 1–9 | national standard, no explicit licence ⚠️ legal review |
| Cervantes PCIC (es), Profile Deutsch / Goethe (de), Cambridge YLE, EVP, Oxford (en) | es, de, en | yes | ❌ copyrighted. Reference only; don't ingest |

**Rules:**
- Keep derived lists as separate data assets with attribution (ShareAlike).
- A Language Pack isn't "production" until its licence register is clean.

### A.3 NLP and script support per language [E/M]
- **Tokenizing and lemmatizing:**
  - Stanza: about 70 languages.
  - UDPipe 2: 70+ languages.
  - spaCy: about 25 trained pipelines.
  - Dedicated segmenters for languages without spaces: jieba/pkuseg (zh), Sudachi/fugashi (ja), PyThaiNLP (th), Kiwi (ko).
- **Reading aids and romanization:**

  | Language / script | Tool | Output |
  |---|---|---|
  | zh | pypinyin | pinyin / zhuyin |
  | ja | UniDic readings | furigana; cutlet for romaji |
  | ko | Revised Romanization libraries | romaja |
  | th | PyThaiNLP | RTGS romanization |
  | ar | CAMeL Tools | diacritization (harakat) |
  | Cyrillic, Devanagari, others | ICU Transliterator, aksharamukha / indic-transliteration | transliteration |

  A level policy decides how many aids to show at each level; the Japanese furigana policy in §2.3 is the template for this.
- **RTL (Arabic, Hebrew, Persian, Urdu):**
  - Shaping needs HarfBuzz and the Unicode bidi algorithm.
  - Karaoke highlighting runs right to left.
  - Mixed-direction glosses need bidi isolates.
  - Nastaliq (Urdu) needs a taller line height.
  - Rendering captions in HTML/Chromium (Remotion) handles all of this. Naive FFmpeg `drawtext` or PIL does not.

### A.4 Speech rate for any language: relative to native, not fixed wpm [E + P]
- Syllable rates differ a lot between languages, but **information rate stays near ~39 bits/s** (Pellegrino et al. 2011; Coupé et al. 2019). https://www.science.org/doi/10.1126/sciadv.aaw2594
- Native reading rates in syllables/s vary widely:

  | ja | es | fr | it | en | de | vi | zh | th |
  |---|---|---|---|---|---|---|---|---|
  | ~7.8 | 7.8 | ~7.2 | ~7.0 | ~6.2 | ~6.0 | ~5.2 | 5.2 | ~5 |

- **Rule:** each Language Pack stores its `native_rate` (in syllables/s, or its own unit such as morae). Each level stores a **fraction of native rate** [P, to be tuned by retention data]:

  | Level | Pre-A1 | A1 | A2 | B1 | B2 | C1–C2 |
  |---|---|---|---|---|---|---|
  | Fraction of native rate | 0.50–0.60 | 0.55–0.65 | 0.65–0.75 | 0.75–0.85 | 0.85–0.95 | 0.95–1.0 |

  Audience Profiles apply a multiplier: toddlers ×0.85, seniors ×0.85–0.9 [P].

  These fractions agree with the earlier English wpm bands in §2.1 (A1 80–100 wpm is about 0.55–0.65 of about 150 wpm).
- Counting speech units needs a per-language syllabifier: pyphen (alphabetic scripts), morae (ja), one per character (zh), one per block (ko).

### A.5 Audience profiles across the whole age range [E + P]
| Profile | Ages | Evidence and constraints | Design rules |
|---|---|---|---|
| toddler | 2–4 | AAP: at most 1 h/day, co-viewing; pacing research (Lillard 2011); "video deficit" under 3 | Songs + TPR, slow cuts, pauses, parent prompts. Made-for-Kids |
| early_reader | 5–7 | YLE Starters; CoE descriptors for 7–10 | Phonics or script basics, sight words, Q&A pauses. MFK |
| kid | 8–12 | YLE Movers/Flyers; CoE descriptors for 7–10 and 11–15 | Serialized stories, quizzes, recurring cast. MFK |
| teen | 13–17 | Not COPPA, but since Aug 2025 YouTube **AI age estimation** (US) turns off personalized ads and adds wellbeing protections for under-18s. https://blog.youtube/news-and-events/extending-our-built-in-protections-to-more-teens-on-youtube/ | School/exam goals (JLPT/HSK/IELTS), pop culture, no mature themes; expect lower ad RPM |
| adult | 18+ | §2.3 | Podcast, story, topic talk, shadowing |
| senior | 60+ | Comprehension drops faster with speech rate; presbycusis; processing speed predicts vocabulary gains; quick metalinguistic explanation hurts. https://pmc.ncbi.nlm.nih.gov/articles/PMC8942782/ · https://pubs.asha.org/doi/10.1044/2019_JSLHR-H-19-0094 | Slower rate, longer pauses, quiet music, boosted 1–4 kHz speech band, large high-contrast captions, one idea per screen, more repetition, practical/travel/grandchildren topics |
| heritage | any | Strong listening, weak literacy and formal register | Reading the script, formal register, less beginner listening and L1 scaffolding |

### A.6 Choosing which slices to produce: the prioritization model [P, fed by E]
Score each candidate slice **(target language × learner market/support language × audience × level band)** on a 1–5 scale for each factor:

| Factor | Weight [P] | Data source |
|---|---|---|
| Demand: learner volume + growth in that market | 0.25 | Duolingo Language Report (by country), Japan Foundation / Hanban learner surveys, search volume |
| Competition gap: few leveled channels for this slice | 0.20 | YouTube search audit per level |
| Revenue: ad RPM of the audience geography + product potential | 0.15 | §1.3; MFK and teen slices score lower |
| Production feasibility: TTS quality tier, NLP maturity, open leveled list | 0.15 | §A.2–A.3 and §4 |
| Reviewer availability: a native reviewer at a sustainable cost | 0.15 | own network / freelancer market |
| Policy risk (inverted): MFK, AI stance, copyright | 0.10 | §1.2 |

**Demand inputs [E]** (Duolingo 2025, https://blog.duolingo.com/2025-duolingo-language-report/):
- **Global top 10:** English (#1 in 154 countries), Spanish, French, Japanese (passed German), German, Korean (passed Italian), Italian, Chinese, Portuguese, Hindi.
- **Growth:** Chinese is the fastest-growing language in 12 markets; Korean is second-fastest in LatAm and Europe.
- **Caveat:** the report excludes learners under 13.

**TTS feasibility tiers [E/P]** (details in §4):

| Tier | Languages | Suitability |
|---|---|---|
| **1** | ~10 major languages (en, es, fr, de, ja, ko, zh, pt, it, hi) | Expressive; suits learners |
| **2** | ~30–60 more | Fluent, but prosody and tone errors. Needs native QA |
| **3** | Low-resource languages | Azure standard voices or open models, some of them NC-licensed. Defer |

**Vendor coverage:**

| Vendor / model | Languages |
|---|---|
| ElevenLabs v4 (launched 2026-09-28) | 90 |
| Gemini TTS | 90+ |
| Azure | 150+ locales |
| OpenAI | ~50, English-optimized |

**Worked result for the three reference examples:** JP-adult ranks highest (demand + gap + feasible), EN-adult second (huge demand, crowded but unleveled), kids EN last (policy/RPM penalty). That is the launch order in §0. Other slices likely to score well [P]:
- **Korean × adult** (growth);
- **Chinese × adult, A1–B1** (growth, gap);
- **Spanish × adult for English speakers** (high-RPM geography);
- **English × senior** (underserved audience).

Rerun the model with real search audits before committing.

### A.7 Format Library × age × level (defaults) [P]
| Format | Ages | Levels | Notes |
|---|---|---|---|
| `song_tpr` | toddler, early_reader | Pre-A1–A1 | Needs licensed or original music |
| `phonics_script_basics` | early_reader, heritage, adult beginners | Pre-A1–A1 | Letters/kana/hangul/pinyin/abjad |
| `graded_story` | all | A1–B2 | Serialized, recurring cast |
| `slow_dialogue_explain_replay` | teen, adult, senior | A1–B1 | Core podcast format |
| `topic_talk` | teen, adult, senior | B1–C2 | Teppei model |
| `shadowing` | teen, adult, senior | any | Pause ≈1.2× line |
| `exam_prep_drill` | teen, adult | per exam (JLPT/HSK/TOPIK/IELTS) | Uses exam aliases from §A.1 |
| `news_digest` | adult, senior | B1+ | Fact-check gate |
| `culture_vlog_narrated` | teen, adult | A2+ | Needs real footage or illustration |

The detailed per-format specs in §2.3 (kids and podcasts) are the worked examples for this table.

---

## 1. Market & platform policy (worked examples: EN, JP, kids)

### 1.1 Comparable channels [E, third-party counts]
| Niche | Channel | Subs | What works |
|---|---|---|---|
| Adult EN | English with Lucy | ~13.7M | On-camera host; course funnel |
| Adult EN | Learn English With TV Series | ~11.4M | Clip commentary (copyright/reuse risk) |
| Adult EN | EnglishClass101 | ~8.7M | Funnel to paid subscription |
| Adult EN | Faceless "slow English podcast" channels (many aimed at Vietnamese learners) | unverified | AI voice, long slow listening; generic and unleveled |
| Kids | Cocomelon / ChuChu / Pinkfong / Super Simple Songs | 200M / 98M / 85M / 47M | Original songs and IP are the moat |
| Kids | Little Fox | ~3M | Graded animated stories → paid library of 3,000+ stories. **The closest model for us** |
| JP | JapanesePod101 | ~2.3M | Funnel to paid subscription |
| JP | Japanese Ammo with Misa | >1M | JLPT grammar search traffic; Patreon |
| JP | Nihongo con Teppei | large podcast audience | Faceless, one human voice, short, 1,000+ episodes, feeds split by level, Patreon |
| JP | Comprehensible Japanese | — | CI with drawings |

**Pattern:** faceless channels do thrive, but I found none with millions of subscribers that is fully AI-voiced. The winners have a recognisable voice or IP, and they funnel viewers into owned products.

### 1.2 YouTube policy constraints [E]
- **Inauthentic content policy (2025-07-15).** It is not allowed to publish content that "looks like it's made with a template… AI-generated content made with generic or unoriginal templates giving the impression of mass production… image slideshows… scrolling text with minimal or no narrative". It *is* allowed to have the same intro/outro and "a series following a set of characters across episodes". https://support.google.com/youtube/answer/1311392
- **January 2026 wave:** 16 AI channels were terminated (35M subscribers in total). Faceless creators report collateral demonetization. Claims that the algorithm favours human faces are anecdotal.
- **Synthetic-content label:** required only for *realistic* altered content, such as a cloned real voice or realistic events. Generic TTS and illustration don't trigger it. Disclose anyway, and always on kids content.
- **Made for Kids / COPPA:** you lose personalized ads, comments, memberships, end screens and the notification bell. RPM falls to about $1–3. FTC fines are up to $53K per violation. Ages 2–9 are Made for Kids with no choice; for ages 10–12, the primary audience decides.
- **YPP (YouTube Partner Program):** today you need 1K subscribers plus 4K watch hours (90-day window). **From 2027-02-01**, new applicants need 8K watch hours in 12 months, and Shorts ad revenue requires 10M Shorts views per 90 days.

**Design rules that follow from the policy**
1. Every episode gets a distinct script, spec'd from the curriculum. Never swap topics into a fixed template.
2. Give each channel a **named host persona or recurring cast** with a consistent voice (licensed or your own), plus season arcs.
3. Use a human-in-the-loop review step, and make it visible: a teacher's note, a corrections log, a "reviewed by" credit.
4. Vary the visuals by segment: vocab cards, quizzes, a story scene, the host.
5. Keep upload cadence sane. The goal is quality per level, not a flood.

### 1.3 Monetization [E/P]
- **Ad RPM:** education has a median of about $10.2 (top quartile about $19.5), but **geography dominates**. A Vietnamese or SEA audience is likely under $1–2. Kids RPM is $1–3. Education Shorts earn about $0.5–1.4.
- **Revenue beyond ads:**
  - Memberships/Patreon perks: transcripts, PDFs, Anki decks, bonus episodes.
  - RSS podcast distribution. Spotify's Partner Program threshold is now 1K listeners and 2K hours in 30 days.
  - Digital products: JLPT vocab books, graded readers, printable worksheets for parents.
  - **The endgame is your own app or library** (Little Fox, Innovative Language).
- **Multi-audio (open to all creators since September 2025):** useful for explanation videos in several native languages (VI, ID, ES). **Turn auto-dub off** on immersion content, because dubbing destroys the lesson.
- **Shorts** are a discovery funnel (word of the day, JLPT quiz), not a revenue source.

### 1.4 Gaps to target
- **N3–N2 Japanese CI.** Current channels cluster at N5–N3.
- **Japanese explained in Vietnamese.** Vietnam's labour and student flows to Japan create demand.
- **Rigorously leveled English podcast A1–C1**, with per-level playlists and PDFs.
- **Bilingual Vietnamese–English kids graded stories.** No Vietnamese-scaffolded equivalent of Little Fox exists. This is a later phase.

---

## 2. Pedagogy → machine-checkable specs (universal rules + worked examples)

### 2.1 Grading levers [E + P]: coverage and repetition are universal; the rate tables below are the EN/JP instances of §A.4
- **Coverage:** ≥95% of script tokens at or below the level's wordlist (van Zeeland & Schmitt 2013), and ≥98% for on-screen text. New words are ≤5% and each must be glossed visually.
- **Repetition:** each target word appears 5–8× in its episode, then is recycled at +1, +3 and +7 episodes and in the season review (the 6–20 encounters research).
- **Speech rate targets [P]:**

| Level | English (words/min) | Japanese level | Japanese (morae/s) |
|---|---|---|---|
| A1 | 80–100 | N5 | 3.5–4.5 |
| A2 | 100–120 | N4 | 4.5–5.3 |
| B1 | 120–140 | N3 | 5.3–6 |
| B2 | 140–165 | N2 | 6–7 |
| C1 | 165–190 | N1 | natural (7+) |
| Kids 2–4 | 70–90, long pauses | | |
| Kids 5–7 | 90–110 | | |
| Kids 8–12 | 110–140 | | |

  Native reference speeds: conversational British English is about 210 wpm, American about 150, and VOA Special English about 90. An "easy Japanese" study found 320–360 morae/min ideal.
- **Sentence length:** A1 about 6–8 words, B1 about 12–15. **Pauses:** 2–4 s at A1/N5.
- **Slow audio must be *re-synthesized* at a slower rate (for example SSML rate 0.8), never time-stretched.**

### 2.2 Wordlists and licensing: EN/JP/kids examples (the general table is §A.2)
| Use | Resource | License |
|---|---|---|
| English backbone | **NGSL 1.2 + NGSL-Spoken** | CC BY-SA ✅ commercial use OK |
| English CEFR tags | CEFR-J v1.5 | Reportedly **CC BY-NC-ND** ⚠️ Verify; build your own A1–C1 mapping on NGSL |
| English CEFR tags | English Vocabulary Profile / Oxford 3000-5000 | ❌ Proprietary. Use for manual reference only |
| Kids | Cambridge YLE Starters/Movers/Flyers 2025 lists | © Cambridge. Use as a topic reference; don't copy |
| Kids | Dolch 220 | Public domain ✅ (Fry is copyrighted) |
| Japanese levels | Tanos N5–N1 vocab and kanji | CC BY ✅ (unofficial; no official JLPT list since 2010) |
| Japanese glosses | JMdict / KANJIDIC (jmdict-simplified JSON) | CC BY-SA ✅ attribution required |
| Japanese readings and accent | UniDic (fugashi) / SudachiPy / OpenJTalk | open ✅ |
| Pitch accent | Kanjium | ⚠️ unclear provenance |

### 2.3 Formats: worked examples (the general library is §A.7)
**Adult English and Japanese podcast**
- **A1–B1 / N5–N3:** slow dialogue, then explanation, then a replay at natural speed.
- **A2–B2 / N4–N2:** a serialized story told with a controlled vocabulary.
- **B1–C1 / N3–N1:** topic talks. Teppei's model works: short, one topic, frequent.
- **Shadowing tracks** as separate short videos or chapters. The pause is about 1.2× the sentence length.
- **Explanations:** at A1–A2 put the L1 help on screen and keep the audio in the target language. From B1 up, everything is in the target language.
- **Seasons:** 10–12 episodes around one theme, with 60–100 target words. About 30% of each episode's target words are recycled, and the season ends with a finale review story.

**Japanese display rules**
| Level | Display |
|---|---|
| N5 | Kana plus romaji toggle, furigana on everything |
| N4 | No romaji, full furigana |
| N3 | Furigana on kanji above N4 |
| N2 | Furigana on kanji above N3 |
| N1 | Rare readings only |

- **Politeness:** です/ます up to N4, casual speech added at N3, keigo as its own theme at N2–N1.
- **Topics that retain viewers:** daily life, food, konbini, travel, seasons and festivals, anime culture, work culture, the host's stories.

**Kids English** [E: AAP guidelines; Lillard 2011 on pacing; Blue's Clues pauses and repetition]
| Age | Length | Format |
|---|---|---|
| 2–4 | 2–4 min | Song or chant with actions (TPR, Total Physical Response). 5–8 words. Heavy chorus. One character. One object on screen at a time. Cuts ≥20 s apart. Question → 3–4 s pause → answer. Parent co-viewing prompts. |
| 5–7 | 4–7 min | Phonics, then a short story, then 2–3 Q&A pauses. Dolch sight words with karaoke highlighting. YLE Starters topics. |
| 8–12 | 8–12 min | Serialized story or mystery with a recurring cast. Quizzes and mini-games. Movers/Flyers vocabulary. |

- No fast cuts and no autoplay-bait.
- Position toddler content as co-viewed songs, not as teaching, because children under 3 learn poorly from video (the "video deficit").

### 2.4 Content matrix: example starting cadence for the three reference slices [P]
| Channel | Level/Age | Length | Frequency |
|---|---|---|---|
| JP pod | N5–N4 | 4–8 min | 3/wk |
| JP pod | N3 | 8–12 min | 2/wk |
| JP pod | N2–N1 | 12–20 min | 1/wk |
| EN pod | A1–A2 | 6–10 min | 3/wk |
| EN pod | B1–B2 | 10–15 min | 2/wk |
| EN pod | C1 | 15–25 min | 1/wk |
| Kids EN | 2–4 | 2–4 min | 3/wk plus a weekly compilation of ≤20 min |
| Kids EN | 5–7 | 4–7 min | 2–3/wk |
| Kids EN | 8–12 | 8–12 min | 1–2/wk |

Plus 3–5 Shorts a week per channel as a funnel.
Launch with fewer levels per channel. For example, JP N5–N3 and EN A2–B1 at about 3–4 episodes a week in total, then expand.

---

## 3. Platform architecture

> **Superseded by [architecture.md](architecture.md).** That document has the language-agnostic multi-agent factory: Language Packs, Level Frameworks, Audience Profiles and Channel Bibles. This section is kept as the original EN/JP sketch. Wherever it names spaCy, Sudachi, furigana or JMdict, read that as "the Language Pack's tool".

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  CURRICULUM  │──▶│   SCRIPT     │──▶│   QA GATES   │──▶│  AUDIO       │──▶│  VIDEO       │
│  Syllabus DB │   │   LLM (JSON) │   │ lexical prof.│   │ TTS per line │   │ Remotion     │
│  wordlists   │   │   + rewrite  │   │ LLM judge x2 │   │ align/timing │   │ templates    │
│  scheduler   │   │     loop     │   │ human review │   │ loudnorm     │   │ thumbnails   │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘
        ▲                                                                          │
        │            ┌──────────────┐   ┌──────────────┐                           ▼
        └────────────│  ANALYTICS   │◀──│  PUBLISH     │◀──────────────── render + mux
         tune bands  │ retention by │   │ YT Data API  │
                     │ level, CTR   │   │ RSS/Spotify  │
                     └──────────────┘   │ PDF/Anki out │
                                        └──────────────┘
```

### 3.1 Core data model
- **Channel:** language, audience, persona or cast, voice map, visual theme, made-for-kids flag.
- **Level:** wordlist, grammar list, rate band, sentence-length band, display rules (furigana/romaji).
- **Season:** theme, target word pool (60–100), grammar points, arc.
- **EpisodeSpec:**
  ```
  {theme, level, format, target_words[5–12], review_words[], grammar_point,
   rate_target, length}
  ```
- **Script** (JSON):
  - `lines[]` with `{speaker, text, reading, romaji, translation{vi,en}, slow?, pause_ms}`
  - `vocab[]`, `grammar_notes[]`, `quiz[]`, `visual_cues[]` (one per concrete noun)
- **Learner-exposure ledger:** tracks how often and where each word has appeared. This drives spaced repetition across episodes.

### 3.2 Pipeline stages
1. **Scheduler.** Picks the next unintroduced words in frequency order (NGSL, tanos), and review words from the +1/+3/+7 slots.
2. **Script generation.** Claude Sonnet 5 with a JSON schema. The level lists sit in the cached prompt. Few-shot examples per format.
3. **Lexical profiler (code, deterministic):**
   - Tokenize: spaCy for English, SudachiPy or fugashi+UniDic for Japanese.
   - Check coverage, new-word count, target-word frequency, sentence length, and grammar above the level.
   - On failure, send a targeted rewrite prompt. Loop at most N times.
4. **LLM judge.** A different model family (Gemini 3.x Pro, or Opus 5.5) returns a JSON issue list: grammar, naturalness, level, facts, kids safety. Only the flagged lines are regenerated.
5. **Japanese readings.** Take readings from UniDic or Sudachi, never from the LLM. Resolve disagreements against JMdict. Romaji via `cutlet`.
6. **Human review UI.** A diff view of the script, audio playback per line, and approve or edit. A native speaker spot-checks Japanese at N5–N3.
7. **TTS per line.** Use a fixed voice per character. Re-render a single line when needed. Slow and natural versions are rendered separately. Insert pauses with pydub or FFmpeg.
8. **Timing.** Use TTS timestamps (ElevenLabs with-timestamps, Azure WordBoundary). Otherwise use WhisperX or ElevenLabs Forced Alignment.
9. **Render.** Remotion compositions per format:
   - podcast: waveform, speaker cards, karaoke subtitles with `<ruby>` furigana, vocab cards, quiz;
   - kids: rigged 2D characters, parallax illustrations, pause timers.
10. **Master.** FFmpeg `loudnorm` to -14 LUFS, then encode.
11. **Publish** via the Data API:
    - Upload as private with `publishAt`.
    - Set `selfDeclaredMadeForKids` and `containsSyntheticMedia` as appropriate.
    - Add the thumbnail, playlist-per-level and caption tracks (JA, romaji, EN, VI).
    - Dubbed audio tracks are added manually in Studio; I found no API for it.
12. **Derivatives, generated from the same script JSON:** transcript PDF, Anki deck, Shorts (word of the day, quiz), RSS audio feed. This is free product inventory for memberships.
13. **Analytics loop.** Retention curve per level and completion rate. Use them to tune the rate and coverage bands.

### 3.3 Automated QA rubric (hard gates ⛔)
| Area | Checks |
|---|---|
| Accuracy | ⛔ No factual errors. ⛔ Correct Japanese readings. Grammar and naturalness by two judges. Translations match JMdict. |
| Level fit | ⛔ Coverage ≥95%. New words within spec. Each target word used ≥5×. Sentence length within band. Measured rate within ±10% of target. No grammar above the level. |
| Engagement | Hook in the first 10 s. Arc or payoff. A call to interact. Visual variety across segments (for the inauthentic-content policy). |
| Kids safety | ⛔ Made-for-Kids flag set. ⛔ No unsafe imitable actions, scary content or commercial persuasion. Pauses are 3–4 s. Shots ≥15 s at ages 2–4. |
| Originality | Similarity check against the last N episodes: scripts and visual layouts must differ materially. |

---

## 4. Recommended tech stack

> The stack is the same for every language. Only the **Language Pack** row choices change: tokenizer, reading-aid engine, TTS voice roster and quality tier (§A.3, §A.6). The EN/JA rows below are the worked examples.

| Layer | Choice | Why / alternatives |
|---|---|---|
| Orchestration | Python (pipeline, NLP) + TypeScript (Remotion). Postgres for curriculum and ledger. A job queue (e.g. a simple worker queue, Temporal later). | The NLP tooling for Japanese is in Python |
| Script LLM | **Claude Sonnet 5** ($2/$10 per M tokens) with structured output and prompt caching | Opus 5.5 ($4/$20) for season planning and judging |
| Checker LLM | Gemini 3.x Pro or Flash (a different model family catches different errors) | |
| EN TTS | **Azure Neural HD** ($22 per M characters; SSML rate control) or **Gemini Flash TTS** (about $0.01/min, only 2 speakers per call; price doubles in January 2027) for bulk. **ElevenLabs v3** (about $0.08 per 1K characters, dialogue mode, timestamps) for premium or hosts. | Kokoro (open source) as a very cheap narrator |
| JA TTS | Azure ja-JP or ElevenLabs for natural speech. **Style-Bert-VITS2 / AivisSpeech** where pitch accent must be correct. | VOICEVOX needs a per-voice credit and has commercial terms ⚠️ |
| JA NLP | fugashi+UniDic / SudachiPy, cutlet, pyopenjtalk (accent), JMdict | |
| Alignment | TTS-native timestamps, then WhisperX, then ElevenLabs Forced Alignment | |
| Images | Flux Kontext / Flux LoRA per character (kids cast). Imagen 4 Fast ($0.02) for podcast scene art. | |
| Kids animation | **2D rigs** (Rive / Lottie / SVG parts in Remotion), not per-episode generation | AI video (Kling 3.0 about $0.08–0.17/s; Veo 3.1 about $0.40/s) only for hero shots. The Sora 2 API was discontinued on 2026-09-24 |
| Music | **ElevenLabs Music** (commercially cleared rights) or public-domain nursery rhymes with your own arrangement | ⚠️ Suno says users are "generally not the owner" after the Warner deal; its models are changing. Avoid it as the backbone of a kids IP |
| Render | **Remotion** (free for ≤3 staff), self-hosted or on Lambda. FFmpeg for mux and loudnorm. | Shotstack at $0.20–0.40 per rendered minute is too expensive at volume |
| Publish | YouTube Data API v3 | Since June 2026, `videos.insert` has its own 100/day bucket at 1 unit per upload. **`captions.insert` costs 400 units**, so an episode with two caption tracks, a thumbnail and a playlist insert uses about 950 of the 10K units, about 10 fully captioned videos a day. Request a quota increase. |

### 4.1 Cost per finished episode (API spend, excluding human time)
| | 15-min EN podcast | 3-min kids song | 20-min JP podcast |
|---|---|---|---|
| Budget stack | ~$0.50–1.20 | ~$1.20–2.50 | ~$0.70–1.80 |
| Premium stack | ~$3–5 | ~$5–15 (with AI video clips) | ~$2–4 |

**Fixed costs:** roughly $50–200 a month (ElevenLabs plan, optional GPU VM, music plan).
**At about 15 episodes a week across channels:** under $150 a month in API spend. The binding constraint is **review time**, about 15–30 minutes per episode.

---

## 5. Roadmap

| Phase | Weeks | Deliverable |
|---|---|---|
| **0. Decisions** | 0–1 | Pick the host personas and names, the L1 support language (VI? EN?), and the launch levels. Get a legal check of wordlist and voice licences. |
| **1. Curriculum engine** | 1–4 | Wordlist ingestion (NGSL, tanos, JMdict); syllabus DB; episode-spec scheduler; script generation plus lexical profiler plus judge loop; CLI to produce a script JSON. **Exit criterion:** 10 JP N4 and 10 EN A2 scripts pass the QA gates and a human review. |
| **2. Audio + render MVP** | 4–7 | Per-line TTS; slow and natural versions; alignment; one Remotion podcast template with karaoke ruby subtitles and vocab cards; FFmpeg mastering. |
| **3. Launch JP + EN podcasts** | 7–10 | Review UI; Data API publishing; PDF, Anki and Shorts derivatives; RSS to Spotify/Apple. 3–4 episodes a week in total. Build watch hours toward YPP before **2027-02-01**. |
| **4. Expand levels + analytics** | 10–20 | Add EN B1–B2 and JP N3–N2 feeds; retention-based tuning; memberships/Patreon with transcripts and decks; multi-language explanation tracks. |
| **5. Kids pilot (premium)** | 20+ | Design an original cast and 2D rigs; commission or arrange songs; ages 5–7 phonics and stories first; COPPA workflow; plan revenue from a parent-facing product, not AdSense. |

---

## 6. Key risks & mitigations
| Risk | Mitigation |
|---|---|
| Demonetized as "inauthentic/mass-produced" | Curriculum-driven unique scripts; recurring cast or host; visual variety; human review credit; moderate cadence; originality QA gate |
| Wrong Japanese readings, pitch accent or keigo | Dictionary-based readings; OpenJTalk-based TTS for accent-critical lines; native spot-checks |
| Wordlist or voice licensing | Build on NGSL, tanos and JMdict; avoid EVP, Oxford and CEFR-J as ingested data; per-voice licence register |
| Kids: COPPA, AI stance, low RPM | Defer; premium originals; correct MFK flags; revenue from products |
| Low RPM from SEA audiences | Products, memberships and Spotify, and an English-medium variant for Western audiences |
| Vendor price and API churn (Gemini TTS doubling, Sora 2 shutdown, Suno terms) | Put each vendor behind an adapter interface (TTS, image, LLM) so they can be swapped |
| YouTube caption quota | Request a quota increase; prioritise which caption tracks to upload |

## 7. Open questions for you
1. **Launch slices.** Which (language × learner market × audience × level) points go first? Run the §A.6 scoring with real search audits. The three examples are only the reference pilots.
2. **Support languages.** Which L1s will explanations and metadata use (EN, VI, ES, ID, …)? This decides RPM and reach.
3. **Face or voice.** Will a real human host or voice appear on any channel? It matters under the 2026 enforcement climate.
4. **Reviewer network.** Is there a native reviewer for each target language you want? This is the real limit on how many languages you can run.
5. **Business model.** Ads first, or eventually an app or library (Little Fox / Innovative Language)?

---

### Main sources
- YouTube policy: https://support.google.com/youtube/answer/1311392 · https://blog.youtube/news-and-events/disclosing-ai-generated-content/ · https://support.google.com/youtube/answer/10774223
- Enforcement and AI in kids content: https://outlierkit.com/resources/youtube-ai-slop-crackdown-2026/ · https://fortune.com/2026/04/01/ai-slop-200-organizations-letter-youtube-google/
- YPP 2027: https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn/
- RPM: https://air.io/en/air-data-findings/which-youtube-niche-makes-the-most-money-in-2026-ranked-by-real-rpm-and-cpm
- Japanese learners by country: https://www.jpf.go.jp/e/project/japanese/survey/result/information/dl/result_overview_e.pdf
- Generalization: https://www.jlpt.jp/e/about/cefr_reference.html · https://www.coe.int/en/web/common-european-framework-reference-languages/bank-of-supplementary-descriptors · https://spraakbanken.gu.se/en/projects/kelly · https://github.com/hermitdave/FrequencyWords · https://kaikki.org · https://www.science.org/doi/10.1126/sciadv.aaw2594 · https://blog.duolingo.com/2025-duolingo-language-report/ · https://blog.youtube/news-and-events/extending-our-built-in-protections-to-more-teens-on-youtube/ · https://pmc.ncbi.nlm.nih.gov/articles/PMC8942782/
- Coverage: https://academic.oup.com/applij/article-abstract/34/4/457/199564 · Pacing: https://www.sciencedaily.com/releases/2011/09/110912075658.htm · AAP: https://publications.aap.org/pediatrics/article/138/5/e20162591/60503/Media-and-Young-Minds
- Wordlists: https://www.newgeneralservicelist.com/new-general-service-list · https://github.com/Bluskyo/JLPT_Vocabulary · https://www.edrdg.org/edrdg/licence.html · https://github.com/scriptin/jmdict-simplified
- Tools and pricing: https://elevenlabs.io/pricing/api · https://ai.google.dev/gemini-api/docs/pricing · https://www.remotion.dev/docs/license/pricing · https://developers.google.com/youtube/v3/determine_quota_cost · https://github.com/litagin02/Style-Bert-VITS2 · https://elevenlabs.io/docs/overview/capabilities/forced-alignment
