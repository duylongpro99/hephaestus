"""Build the `en` pack's leveled lexicon from commercially licensed sources.

    uv run python -m packs.en.ingest           # download sources, build lexicon.jsonl, install WordNet
    uv run python -m packs.en.ingest --check   # verify checksums and print entry counts per level

Levels come from frequency rank, a proxy recorded in research.md §A.2 rule 3 and calibrated in
packs/en/calibration.md. EVP, Oxford 3000 and CEFR-J are never ingested.
"""

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

PACK_DIR = Path(__file__).resolve().parent
DATA_DIR = PACK_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
WN_DATA_DIR = RAW_DIR / "wn"
LEXICON_PATH = DATA_DIR / "lexicon.jsonl"
SUPPLEMENT_PATH = DATA_DIR / "supplement.yaml"
LICENSES_PATH = PACK_DIR / "licenses.yaml"

# Rank cutoffs: a lemma at or below the rank gets the level. Calibrated in calibration.md.
RANK_CUTOFFS = (("A1", 500), ("A2", 1000))
LEVEL_ABOVE_CUTOFFS = "B1"

NGSL_BASE = "https://www.newgeneralservicelist.com/s/"
NGSL_ATTRIBUTION = (
    "Browne, C., Culligan, B., & Phillips, J. (2013). The New General Service List. "
    "Licensed under CC BY-SA 4.0. https://www.newgeneralservicelist.com"
)
NGSL_SPOKEN_ATTRIBUTION = (
    "Browne, C., & Culligan, B. (2017). The New General Service List - Spoken (NGSL-Spoken). "
    "Licensed under CC BY-SA 4.0. https://www.newgeneralservicelist.com"
)
OEWN_VERSION = "2025"
OEWN_ATTRIBUTION = (
    "McCrae, J. P., et al. Open English WordNet 2025. Licensed under CC BY 4.0. https://en-word.net"
)

SOURCES = {
    "ngsl_forms": {
        "dataset": "NGSL 1.2",
        "file": "NGSL_12_lemmatized_for_research.csv",
        "url": NGSL_BASE + "NGSL_12_lemmatized_for_research.csv",
        "license": "CC BY-SA 4.0",
        "attribution": NGSL_ATTRIBUTION,
    },
    "ngsl_stats": {
        "dataset": "NGSL 1.2",
        "file": "NGSL_12_stats.csv",
        "url": NGSL_BASE + "NGSL_12_stats.csv",
        "license": "CC BY-SA 4.0",
        "attribution": NGSL_ATTRIBUTION,
    },
    "spoken_forms": {
        "dataset": "NGSL-Spoken 1.2",
        "file": "NGSL-Spoken_12_lemmatized_for_research.csv",
        "url": NGSL_BASE + "NGSL-Spoken_12_lemmatized_for_research.csv",
        "license": "CC BY-SA 4.0",
        "attribution": NGSL_SPOKEN_ATTRIBUTION,
    },
    "spoken_stats": {
        "dataset": "NGSL-Spoken 1.2",
        "file": "NGSL-Spoken_12_stats.csv",
        "url": NGSL_BASE + "NGSL-Spoken_12_stats.csv",
        "license": "CC BY-SA 4.0",
        "attribution": NGSL_SPOKEN_ATTRIBUTION,
    },
    "oewn": {
        "dataset": f"Open English WordNet {OEWN_VERSION}",
        "file": f"english-wordnet-{OEWN_VERSION}.xml.gz",
        "url": f"https://en-word.net/static/english-wordnet-{OEWN_VERSION}.xml.gz",
        "license": "CC BY 4.0",
        "attribution": OEWN_ATTRIBUTION,
    },
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "yt-factory-ingest/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        dest.write_bytes(response.read())


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace")


def parse_forms(text: str) -> dict[str, list[str]]:
    """Parse a 'lemmatized for research' CSV: headword first, then its inflected forms."""
    families: dict[str, list[str]] = {}
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip().lower() for c in row if c.strip()]
        if not cells or cells[0].startswith("##"):
            continue
        head, forms = cells[0], cells[1:]
        families[head] = [f for f in dict.fromkeys(forms) if f != head]
    return families


def parse_ranks(text: str) -> dict[str, int]:
    """Parse a stats CSV whose first column is the lemma and second the rank."""
    ranks: dict[str, int] = {}
    reader = csv.reader(io.StringIO(text))
    next(reader)  # header
    for row in reader:
        # Skip rows without a numeric rank; NGSL-Spoken 1.2 has one spreadsheet error ("TRUE,#N/A").
        if len(row) >= 2 and row[0].strip() and row[1].strip().isdigit():
            ranks[row[0].strip().lower()] = int(row[1])
    return ranks


def level_for_rank(rank: int | None) -> str | None:
    if rank is None:
        return None
    for level, cutoff in RANK_CUTOFFS:
        if rank <= cutoff:
            return level
    return LEVEL_ABOVE_CUTOFFS


def lower_level(a: str | None, b: str | None) -> str | None:
    order = ["PreA1", "A1", "A2", "B1", "B2", "C1", "C2"]
    present = [x for x in (a, b) if x is not None]
    return min(present, key=order.index) if present else None


def build_lexicon(raw_dir: Path, supplement: dict[str, str]) -> list[dict]:
    ngsl_forms = parse_forms(read_text(raw_dir / SOURCES["ngsl_forms"]["file"]))
    ngsl_ranks = parse_ranks(read_text(raw_dir / SOURCES["ngsl_stats"]["file"]))
    spoken_forms = parse_forms(read_text(raw_dir / SOURCES["spoken_forms"]["file"]))
    spoken_ranks = parse_ranks(read_text(raw_dir / SOURCES["spoken_stats"]["file"]))

    entries = []
    for head in sorted(set(ngsl_forms) | set(spoken_forms) | set(supplement)):
        rank, spoken_rank = ngsl_ranks.get(head), spoken_ranks.get(head)
        level = lower_level(level_for_rank(rank), level_for_rank(spoken_rank))
        sources = [name for name, ok in (("ngsl", head in ngsl_forms), ("ngsl_spoken", head in spoken_forms)) if ok]
        if head in supplement:
            level = lower_level(level, supplement[head])
            sources.append("supplement")
        forms = list(dict.fromkeys(ngsl_forms.get(head, []) + spoken_forms.get(head, [])))
        entries.append({
            "headword": head,
            "forms": forms,
            "rank": rank,
            "spoken_rank": spoken_rank,
            "level": level,
            "sources": sources,
        })
    return entries


def load_supplement(path: Path = SUPPLEMENT_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {word.lower(): level for level, words in data.get("levels", {}).items() for word in words}


def write_licenses(checksums: dict[str, str]) -> None:
    register = {
        "pack": "en",
        "note": "Every dataset the en pack ingests. EVP, Oxford 3000 and CEFR-J are reference only and never ingested.",
        "sources": [
            {
                "id": key,
                "dataset": src["dataset"],
                "file": src["file"],
                "url": src["url"],
                "license": src["license"],
                "attribution": src["attribution"],
                "retrieved": date.today().isoformat(),
                "sha256": checksums[key],
            }
            for key, src in SOURCES.items()
        ],
        "derived": [
            {
                "file": "data/lexicon.jsonl",
                "license": "CC BY-SA 4.0",
                "note": "Derived from NGSL 1.2 and NGSL-Spoken 1.2 (ShareAlike) plus data/supplement.yaml.",
            },
            {
                "file": "data/supplement.yaml",
                "license": "CC BY-SA 4.0",
                "note": "Own work: everyday words missing from or ranked too low in NGSL, levelled by the project.",
            },
        ],
    }
    LICENSES_PATH.write_text(
        "# Generated by `python -m packs.en.ingest`. Licence register for the en pack (architecture §13).\n"
        + yaml.safe_dump(register, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )


def install_wordnet(path: Path) -> None:
    import wn

    wn.config.data_directory = WN_DATA_DIR
    if not wn.lexicons(lexicon="oewn"):
        wn.add(path, progress_handler=None)


def write_lexicon(entries: list[dict]) -> None:
    with LEXICON_PATH.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ingest() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for key, src in SOURCES.items():
        dest = RAW_DIR / src["file"]
        if not dest.exists():
            print(f"downloading {src['url']}")
            download(src["url"], dest)
        checksums[key] = sha256_of(dest)
    entries = build_lexicon(RAW_DIR, load_supplement())
    write_lexicon(entries)
    write_licenses(checksums)
    install_wordnet(RAW_DIR / SOURCES["oewn"]["file"])
    print(f"wrote {LEXICON_PATH.relative_to(PACK_DIR.parents[1])}: {len(entries)} entries")
    print_counts(entries)


def print_counts(entries: list[dict]) -> None:
    counts = Counter(entry["level"] for entry in entries)
    for level in sorted(counts, key=lambda lv: ["PreA1", "A1", "A2", "B1", "B2", "C1", "C2"].index(lv)):
        print(f"  {level}: {counts[level]}")


def check() -> int:
    register = yaml.safe_load(LICENSES_PATH.read_text(encoding="utf-8"))
    ok = True
    for src in register["sources"]:
        path = RAW_DIR / src["file"]
        if not path.exists():
            print(f"MISSING  {src['file']} (run `python -m packs.en.ingest`)")
            ok = False
            continue
        actual = sha256_of(path)
        status = "OK      " if actual == src["sha256"] else "MISMATCH"
        ok &= actual == src["sha256"]
        print(f"{status} {src['file']} sha256={actual[:16]}…")
    entries = [json.loads(line) for line in LEXICON_PATH.read_text(encoding="utf-8").splitlines()]
    rebuilt = build_lexicon(RAW_DIR, load_supplement()) if ok else entries
    if rebuilt != entries:
        print("STALE    data/lexicon.jsonl differs from a rebuild; rerun the ingest")
        ok = False
    print(f"lexicon entries: {len(entries)}")
    print_counts(entries)
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify checksums and print level counts")
    args = parser.parse_args()
    sys.exit(check() if args.check else ingest())


if __name__ == "__main__":
    main()
