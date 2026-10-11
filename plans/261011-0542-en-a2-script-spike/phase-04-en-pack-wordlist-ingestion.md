---
phase: 4
title: "en pack and wordlist ingestion"
status: pending
priority: P1
effort: "1.5d"
dependencies: [3]
---

# Phase 4: en pack and wordlist ingestion

## Goal
Build the parts of the `en` Language Pack that the profiler and A3 need. It is backed by an NGSL-derived A1/A2 lexicon, Open English WordNet and a clean licence register.

## Files to Create / Modify
- Create: `factory/tools/language_pack.py`: the §4.0 `LanguagePack` Protocol, plus the `Token` and `Level` types.
- Create: `packs/en/ingest.py`. It:
  1. downloads NGSL 1.2 (lemmatized, with word families) and NGSL-Spoken into `packs/en/data/raw/` and records each sha256;
  2. assigns levels by rank: A1 is NGSL rank ≤500, A2 is rank ≤1000, and NGSL-Spoken words take the lower of their two levels;
  3. writes `packs/en/data/lexicon.jsonl` with the headword, family forms, rank and level of each entry.
- Create: `packs/en/licenses.yaml`: for NGSL, NGSL-Spoken and Open English WordNet, the URL, licence, attribution text, retrieval date and sha256.
- Create: `packs/en/pack.py`: `EnPack`, with `rate_unit = "wpm"` and these methods:
  - `tokenize`: spaCy `en_core_web_sm`, returning surface, lemma and POS.
  - `lemma_level`: looks up the lemma first and the family form second.
  - `speech_units`: the word count.
  - `dictionary_gloss`: the first WordNet definition, used as the simple-English gloss.
  - `simpler_synonyms(lemma, level)`: WordNet synonyms filtered to the given level or below.
- Create: `packs/en/calibration.md`: notes from a manual spot-check of 50 words against EVP. This is reference only; EVP data is never stored.
- Create: `packs/en/tests/test_conformance.py`

## Tasks & Steps
1. Before writing the parser, check the current NGSL file format and licence on newgeneralservicelist.com.
2. Treat these as always in-level: punctuation, numerals, proper nouns and cast names. Contractions such as `don't` are split by spaCy, and each part is looked up separately.
3. Calibrate the 500/1000 cutoffs. Sample 25 words near each cutoff, compare them by hand with EVP levels, move a cutoff if more than 20% disagree, and record the result in `calibration.md`.
4. Write the conformance fixtures:
   - `went` resolves to `go`, level A1;
   - `running` resolves to `run`;
   - a known word ranked above 1000 returns None or a level above A2;
   - `don't` counts as two in-level tokens;
   - `simpler_synonyms("purchase", "A2")` contains `buy`.

## Verification
- `uv run pytest packs/en/tests` passes.
- `uv run python -m packs.en.ingest --check` prints the entry count for each level and confirms that each sha256 matches `licenses.yaml`.
