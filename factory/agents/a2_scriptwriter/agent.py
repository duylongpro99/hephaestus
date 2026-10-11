"""A2 Scriptwriter: one structured call, EpisodeSpec -> Script."""

from pathlib import Path

from pydantic import ValidationError

from factory.adapters.llm.base import LLMError, LLMProvider
from factory.agents.drafts import draft_models, to_draft_dict, to_script
from factory.agents.prefix import system_blocks
from factory.artifacts import ADAPTER_SOURCES, station_version
from factory.config import ResolvedConfig
from factory.contracts import CostEntry, EpisodeSpec, Script
from factory.tools.language_pack import LanguagePack

STATION = "a2_scriptwriter"
HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompt.md"
EXAMPLE_PATH = HERE / "example_script.json"


def version(identity: str) -> str:
    """`identity` is the role's provider/model/params identity from config/llm.yaml."""
    return station_version(identity, PROMPT_PATH, EXAMPLE_PATH, Path(__file__).resolve(),
                           HERE.parent / "drafts.py", HERE.parent / "prefix.py", *ADAPTER_SOURCES)


def build_system(config: ResolvedConfig, pack: LanguagePack) -> list[str]:
    support = config.channel.support_languages
    example = Script.model_validate_json(EXAMPLE_PATH.read_text(encoding="utf-8"))
    return system_blocks(
        PROMPT_PATH.read_text(encoding="utf-8"), config, pack,
        example=to_draft_dict(example, config.pack.code, support),
    )


def build_user(spec: EpisodeSpec, config: ResolvedConfig) -> str:
    rate = config.band.rate
    low, high = spec.length_min
    # Roughly 15% of an episode is pauses; this gives the writer a word budget to aim for.
    words_low, words_high = (round(m * 0.85 * rate.midpoint, -1) for m in (low, high))
    return (
        "Write the episode for this Episode Spec.\n\n"
        f"{spec.model_dump_json(indent=2)}\n\n"
        f"Length guide: about {words_low:.0f}-{words_high:.0f} spoken words in total, "
        f"so the estimate (words / {rate.midpoint:g} {rate.unit} + pauses) lands inside "
        f"{low:g}-{high:g} minutes."
    )


def write_script(
    spec: EpisodeSpec, config: ResolvedConfig, pack: LanguagePack, llm: LLMProvider,
) -> tuple[Script, list[CostEntry]]:
    support = config.channel.support_languages
    draft_model = draft_models(config.pack.code, tuple(support))
    result = llm.structured(
        station=STATION,
        system=build_system(config, pack),
        user=build_user(spec, config),
        output_model=draft_model,
    )
    try:
        script = to_script(result.parsed, spec.episode_id, config.pack.code, support)
    except ValidationError as exc:
        raise LLMError(f"{STATION}: draft is not a valid Script: {exc}", result.costs) from exc
    return script, result.costs
