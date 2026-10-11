"""Cached prompt prefix shared by the script stations (architecture §8).

Order, most stable first: station instructions, ResolvedConfig, level wordlist and grammar,
few-shot example, then a cache breakpoint. The volatile spec or script goes in the user turn.
Nothing here may contain a timestamp or a run id.
"""

import json

from factory.config import ResolvedConfig
from factory.tools.language_pack import LanguagePack


def wordlist_block(config: ResolvedConfig, pack: LanguagePack) -> str:
    groups = pack.level_wordlist(config.level)
    parts = [f"# Wordlist: words learners at {config.level} know ({config.pack.code})"]
    for level, words in groups.items():
        parts.append(f"## {level} ({len(words)} words)\n" + ", ".join(words))
    parts.append(f"# Grammar allowed at {config.level}\n" + "\n".join(f"- {g}" for g in config.band.grammar))
    return "\n\n".join(parts)


def system_blocks(
    instructions: str, config: ResolvedConfig, pack: LanguagePack, example: dict | None = None,
) -> list[str]:
    """Stable system text, in cache order. Providers place their cache breakpoint after the last block."""
    blocks = [
        instructions,
        "# Resolved configuration\n" + config.canonical_json(),
        wordlist_block(config, pack),
    ]
    if example is not None:
        blocks.append("# Example of the output shape (shorter than a real episode)\n"
                      + json.dumps(example, ensure_ascii=False, sort_keys=True))
    return blocks
