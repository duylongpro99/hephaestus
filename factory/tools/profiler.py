"""Deterministic lexical profiler: Script + EpisodeSpec + ResolvedConfig -> LevelReport.

It talks to the target language only through the LanguagePack interface, and reads every
threshold from the resolved level band.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean

from factory.config import ResolvedConfig
from factory.contracts import EpisodeSpec, GateFailure, LevelReport, OffLevelToken, Script
from factory.contracts.level_report import SentenceLengthStats
from factory.tools.language_pack import LanguagePack, Token, at_or_below
from factory.tools.rate_estimator import duration_within, estimate_duration_min, speech_units


@dataclass(frozen=True)
class TextUnit:
    id: str
    text: str
    spoken: bool  # spoken lines count for repetition, sentence length and duration


def text_units(script: Script) -> list[TextUnit]:
    units = []
    for segment in script.segments:
        units += [TextUnit(line.id, line.text, True) for line in segment.lines]
        for item in segment.items:  # on-screen quiz text counts for coverage only
            units.append(TextUnit(item.id, " ".join([item.question, *item.options]), False))
    return units


def is_word(token: Token) -> bool:
    """A token a listener hears as (part of) a word; clitics such as n't join the previous word."""
    return not token.is_punct and not token.surface.startswith("'") and token.surface.lower() != "n't"


def is_content(token: Token, names: set[str]) -> bool:
    """A token that carries vocabulary load. Clitics, numbers, names and interjections do not."""
    return is_word(token) and not (
        token.is_num or token.is_proper or token.pos == "INTJ" or token.surface.lower() in names
    )


def matches(token: Token, forms: set[str]) -> bool:
    return token.lemma in forms or token.surface.lower() in forms


def phrase_count(text: str, phrase: str) -> int:
    normalized = text.lower().replace("\u2019", "'")
    return len(re.findall(rf"(?<![\w']){re.escape(phrase)}(?![\w'])", normalized))


def replay_mismatches(script: Script) -> list[str]:
    """Replay line ids whose text differs from the dialogue, line for line."""
    dialogue = [line for s in script.segments if s.type == "dialogue" for line in s.lines]
    replay = [line for s in script.segments if s.type == "replay" for line in s.lines]
    if not replay:
        return []
    bad = [r.id for d, r in zip(dialogue, replay) if d.text.strip() != r.text.strip()]
    bad += [r.id for r in replay[len(dialogue):]]
    if len(replay) < len(dialogue):
        bad.append(f"missing {len(dialogue) - len(replay)} replay line(s)")
    return bad


def profile(script: Script, spec: EpisodeSpec, config: ResolvedConfig, pack: LanguagePack) -> LevelReport:
    band = config.band
    level = config.level
    targets = [w.lower() for w in spec.target_words]
    single_targets = {t: {t, *pack.lemma_forms(t)} for t in targets if " " not in t}
    phrase_targets = [t for t in targets if " " in t]
    target_forms = set().union(*single_targets.values()) if single_targets else set()
    review_forms = {f for w in spec.review_words for f in (w.lower(), *pack.lemma_forms(w.lower()))}
    allowed = target_forms | review_forms
    names = {c.lower() for c in spec.cast} | {m.id.lower() for m in config.channel.cast}
    names.add(config.channel.persona.name.lower())

    content_count = in_level_count = 0
    content_lemmas: set[str] = set()
    new_lemmas: set[str] = set()
    off_level: list[OffLevelToken] = []
    target_counts: Counter[str] = Counter({w: 0 for w in targets})
    sentence_lengths: list[tuple[str, int]] = []

    for unit in text_units(script):
        tokens = pack.tokenize(unit.text)
        words_per_sentence: dict[int, int] = defaultdict(int)
        for token in tokens:
            if unit.spoken and is_word(token):
                words_per_sentence[token.sentence] += 1
            if unit.spoken:
                for target, forms in single_targets.items():
                    if matches(token, forms):
                        target_counts[target] += 1
            if not is_content(token, names):
                continue
            content_count += 1
            content_lemmas.add(token.lemma)
            if matches(token, allowed):
                in_level_count += 1
                if matches(token, target_forms):
                    new_lemmas.add(token.lemma)
                continue
            token_level = pack.lemma_level(token, config.framework)
            if at_or_below(token_level, level):
                in_level_count += 1
            else:
                new_lemmas.add(token.lemma)
                off_level.append(OffLevelToken(
                    line_id=unit.id, surface=token.surface, lemma=token.lemma, level=token_level,
                ))
        sentence_lengths += [(unit.id, n) for n in words_per_sentence.values()]
        if unit.spoken:
            for phrase in phrase_targets:
                target_counts[phrase] += phrase_count(unit.text, phrase)

    in_level_ratio = round(in_level_count / content_count, 4) if content_count else 1.0
    new_word_ratio = round(len(new_lemmas) / len(content_lemmas), 4) if content_lemmas else 0.0

    low, high = band.sentence_length
    lengths = [n for _, n in sentence_lengths] or [0]
    long_lines = sorted({line_id for line_id, n in sentence_lengths if n > high})
    long_share = round(sum(n > high for n in lengths) / len(lengths), 4)
    sentence_stats = SentenceLengthStats(
        mean=round(mean(lengths), 2), min=min(lengths), max=max(lengths), band=(low, high),
        sentence_count=len(sentence_lengths), long_lines=long_lines, long_share=long_share,
    )
    duration = estimate_duration_min(script, pack, band.rate)

    failures: list[GateFailure] = []
    if in_level_ratio < band.coverage_min:
        lines = sorted({t.line_id for t in off_level})
        words = sorted({t.lemma for t in off_level})
        failures.append(GateFailure(
            gate="coverage",
            detail=f"in-level ratio {in_level_ratio:.1%} < {band.coverage_min:.0%}; off-level: {', '.join(words)}",
            line_ids=lines,
        ))
    if new_word_ratio > band.new_word_max:
        failures.append(GateFailure(
            gate="new_words",
            detail=f"new-word ratio {new_word_ratio:.1%} > {band.new_word_max:.0%} "
                   f"({len(new_lemmas)} new of {len(content_lemmas)} distinct lemmas)",
        ))
    short = {w: n for w, n in target_counts.items() if n < band.target_repetition_min}
    if short:
        failures.append(GateFailure(
            gate="target_repetition",
            detail="below {} uses: {}".format(
                band.target_repetition_min, ", ".join(f"{w}={n}" for w, n in sorted(short.items()))),
        ))
    mean_ok = sentence_stats.mean <= high and (band.sentence_length_gate == "ceiling" or sentence_stats.mean >= low)
    if not mean_ok or long_share > band.long_sentence_share_max:
        failures.append(GateFailure(
            gate="sentence_length",
            detail=f"mean {sentence_stats.mean} words (band {low}-{high}); "
                   f"{long_share:.0%} of sentences longer than {high} (max {band.long_sentence_share_max:.0%})",
            line_ids=long_lines,
        ))
    if not duration_within(duration, spec.length_min):
        failures.append(GateFailure(
            gate="duration",
            detail=f"estimated {duration} min outside {spec.length_min[0]}-{spec.length_min[1]} min",
        ))
    missing_gloss = _missing_glosses(script, targets, config.channel.support_languages)
    if missing_gloss:
        failures.append(GateFailure(gate="vocab_gloss", detail="; ".join(missing_gloss)))

    mismatched = replay_mismatches(script)
    if mismatched:
        failures.append(GateFailure(
            gate="replay_mismatch",
            detail="the replay must repeat the dialogue line for line",
            line_ids=[m for m in mismatched if not m.startswith("missing")],
        ))

    return LevelReport(
        episode_id=script.episode_id,
        level=level,
        config_hash=config.config_hash,
        content_token_count=content_count,
        in_level_ratio=in_level_ratio,
        new_word_ratio=new_word_ratio,
        off_level_tokens=off_level,
        target_word_counts=dict(target_counts),
        sentence_length=sentence_stats,
        word_count=speech_units(script, pack),
        estimated_duration_min=duration,
        gate_failures=failures,
    )


def _missing_glosses(script: Script, targets: list[str], languages: list[str]) -> list[str]:
    vocab = {item.word.lower(): item for item in script.vocab}
    problems = []
    for word in targets:
        item = vocab.get(word)
        if item is None or not item.is_target:
            problems.append(f"target word '{word}' missing from vocab")
            continue
        absent = [lang for lang in languages if not item.gloss.get(lang, "").strip()]
        if absent:
            problems.append(f"'{word}' has no gloss in {', '.join(absent)}")
    return problems


def format_report(report: LevelReport) -> str:
    """A human-readable summary of a LevelReport."""
    s = report.sentence_length
    lines = [
        f"{report.episode_id} @ {report.level}: {'PASS' if report.passed else 'FAIL'}",
        f"  in-level ratio  {report.in_level_ratio:.1%} of {report.content_token_count} content tokens",
        f"  new-word ratio  {report.new_word_ratio:.1%}",
        f"  sentence length mean {s.mean} (band {s.band[0]}-{s.band[1]}), max {s.max}, long {s.long_share:.0%}",
        f"  words {report.word_count}, estimated {report.estimated_duration_min} min",
        "  targets         " + ", ".join(f"{w}={n}" for w, n in report.target_word_counts.items()),
    ]
    if report.off_level_tokens:
        lines.append("  off-level       " + ", ".join(
            f"{t.surface}({t.level or '-'})@{t.line_id}" for t in report.off_level_tokens))
    for failure in report.gate_failures:
        lines.append(f"  ✗ {failure.gate}: {failure.detail}")
    return "\n".join(lines)
