# en pack: rank-cutoff calibration

**Date:** 2026-10-11. **Status:** provisional; the EVP levels need human verification (see the caveat).

## Method

The lexicon assigns A1 to NGSL rank ≤500 and A2 to rank ≤1000 (research.md §A.2 rule 3, a [P]
estimate). Words from NGSL-Spoken take the lower of their two levels. To check the cutoffs,
25 words around each cutoff were compared with their lowest English Vocabulary Profile (EVP)
level. The rule was to move a cutoff if more than 20% disagree.

**Caveat:** EVP could not be opened from the build environment (englishprofile.org returned 404,
Cambridge Dictionary returned 403). The EVP levels below are the implementer's recollection of
EVP and have **not** been checked against EVP itself. Nothing from EVP is stored in the
lexicon. Before the cutoffs are treated as final, a person should check these 50 words in EVP
Online and correct this table.

## Results

Each cell shows word (NGSL rank) and the recalled lowest EVP level. ✓ means the band agrees with
the lexicon level for the A2 gate (at or below A2 versus above A2).

### Around the A1 cutoff (ranks 488–512)

| Lexicon A1 (≤500) | EVP | Lexicon A2 (501–512) | EVP |
|---|---|---|---|
| front (488) | A1 | claim (501) | B2 |
| explain (489) | A2 | relationship (502) | B1 |
| door (490) | A1 | travel (503) | A1 |
| outside (491) | A1 | enjoy (504) | A1 |
| behind (492) | A2 | death (505) | B1 |
| economic (493) | B1 | nice (506) | A1 |
| site (494) | B1 | amount (507) | B1 |
| approach (495) | B2 | improve (508) | A2 |
| teacher (496) | A1 | picture (509) | A1 |
| land (497) | B1 | boy (510) | A1 |
| charge (498) | B1 | regard (511) | B2 |
| finally (499) | A2 | organization (512) | B1 |
| sign (500) | A2 | | |

Exact A1 agreement for ranks 488–500 is 5 of 13 (62% disagree). At the A2 gate's resolution
(at or below A2), 8 of 25 words that the lexicon puts at A2 or below are B1+ in EVP (32%).

### Around the A2 cutoff (ranks 988–1012)

| Lexicon A2 (≤1000) | EVP | Lexicon B1 (>1000) | EVP |
|---|---|---|---|
| immediately (988) | B1 | difficulty (1001) | B1 |
| welcome (989) | A1 | purchase (1002) | B1 |
| smile (990) | A2 | shoot (1003) | B1 |
| communication (991) | B1 | announce (1004) | B1 |
| agent (992) | B1 | unless (1005) | B1 |
| traditional (993) | B1 | independent (1006) | B1 |
| replace (994) | B1 | recommend (1007) | B1 |
| judge (995) | B1 | survey (1008) | B1 |
| herself (996) | A2 | majority (1009) | B1 |
| suddenly (997) | A2 | stick (1010) | B1 |
| generation (998) | B1 | request (1011) | B1 |
| estimate (999) | B2 | rich (1012) | A2 |
| favorite (1000) | A1 | | |

Disagreement: 8 of 13 words below the cutoff are B1+ and 1 of 12 above it is A2, so 9 of 25
disagree (36%).

### Extra bands checked

Ranks 738–762: 12 of 25 are B1+ (48%). Ranks 838–862: 14 of 25 are B1+ (56%).

## Decision

- **Cutoffs stay at 500 and 1000.** Disagreement is above 20% at both cutoffs, but it is just as
  high at ranks 750 and 850, so moving the A2 cutoff only trades one error for another.
  Frequency rank is a weak proxy for learner level in the 500–1000 band, because abstract
  written-register words (economic, relationship, strategy) are as frequent as concrete
  everyday ones.
- **Strictness errors are fixed with an own-work supplement.** NGSL omits or ranks low many
  everyday survival words (hello 2803, breakfast 1819, milk 1789; apple, hungry and delicious
  are absent). `data/supplement.yaml` lists 242 everyday words by topic, written by the
  project. A word in it takes the lower of the two levels.
- **Leniency errors are left to the review panel.** Abstract words ranked ≤1000 that EVP puts
  at B1 (for example communication, generation, economic) pass the lexical gate. Reviewer T's
  level-fit check is the backstop, and the phase 7 report compares the profiler's verdict with
  Reviewer T's to measure how often this matters.
- **Revisit** if Reviewer T flags above-level words that the profiler passed in more than 2 of
  the 10 spike scripts. The likely fix is an own-work demotion list for abstract words.

## Other rules

- Punctuation, numerals, proper nouns and possessive `'s` are always in-level.
- spaCy splits contractions (`don't` → `do` + `n't`), and each part is levelled through its
  lemma (`do`, `not`).
- NGSL-Spoken 1.2's stats file has one broken row (`TRUE,#N/A`); the ingest skips rows without a
  numeric rank.
