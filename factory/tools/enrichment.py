"""C2 Script Enrichment: reading aids per line, delegated to the Language Pack (architecture §7)."""

from factory.contracts import Enrichment, HintSpan, LineEnrichment, RubySpan, Script
from factory.tools.language_pack import LanguagePack


def enrich(script: Script, pack: LanguagePack, policy: str) -> Enrichment:
    """`policy` names the level's display policy; the pack decides what it means (e.g. which kanji get ruby)."""
    lines = []
    for line in script.iter_lines():
        entry = LineEnrichment(
            line_id=line.id,
            ruby=[RubySpan(start=r.start, end=r.end, text=r.text) for r in pack.reading_aids(line.text, policy)],
            romanization=pack.romanize(line.text),
            hints=[HintSpan(start=h.start, end=h.end, kind=h.kind, value=h.value)
                   for h in pack.pronunciation_hints(line.text)],
        )
        if entry.ruby or entry.romanization or entry.hints:
            lines.append(entry)
    return Enrichment(episode_id=script.episode_id, policy=policy, lines=lines)
