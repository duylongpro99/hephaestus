"""A9 Packager: title, description and tags per support language, plus chapters (architecture §3).

The copy is one structured LLM call; chapters, flags and the video pointer are filled in code.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from factory.adapters.llm.base import LLMError, LLMProvider
from factory.artifacts import ADAPTER_SOURCES, station_version
from factory.config import ResolvedConfig
from factory.contracts import Chapter, CostEntry, EpisodeSpec, PublishPackage, RenderProps, Script

STATION = "a9_packager"
PROMPT = """You write YouTube metadata for one episode of a language-learning channel.

For every language listed in `languages`, write in that language:
- `title`: at most 80 characters; name what happens and the level.
- `description`: two to four sentences; say what the learner hears and list the target words.
- `tags`: five to ten short tags.

`thumbnail_text` is at most four words for the thumbnail, in the first listed language.
Return one entry in `copies` per language, with its language code."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalizedCopy(_Closed):
    language: str
    title: str
    description: str
    tags: list[str]


class PackagerCopy(_Closed):
    copies: list[LocalizedCopy]
    thumbnail_text: str


def version(identity: str) -> str:
    return station_version(identity, Path(__file__).resolve(), *ADAPTER_SOURCES)


def build_user(spec: EpisodeSpec, script: Script, config: ResolvedConfig) -> str:
    return json.dumps({
        "languages": config.channel.support_languages,
        "channel": config.channel.channel,
        "level": spec.level,
        "theme": spec.theme,
        "target_words": spec.target_words,
        "title_working": script.title_working,
        "hook": script.hook,
        "vocab": [item.model_dump() for item in script.vocab],
    }, ensure_ascii=False)


def write_copy(
    spec: EpisodeSpec, script: Script, config: ResolvedConfig, llm: LLMProvider,
) -> tuple[PackagerCopy, list[CostEntry]]:
    result = llm.structured(station=STATION, system=[PROMPT], user=build_user(spec, script, config),
                            output_model=PackagerCopy)
    copy = result.parsed
    missing = set(config.channel.support_languages) - {c.language for c in copy.copies}
    if missing:
        raise LLMError(f"{STATION}: no copy for {', '.join(sorted(missing))}", result.costs)
    return copy, result.costs


def package(
    spec: EpisodeSpec, config: ResolvedConfig, props: RenderProps, video_uri: str, copy: PackagerCopy,
) -> PublishPackage:
    wanted = config.channel.support_languages
    by_lang = {c.language: c for c in copy.copies if c.language in wanted}
    return PublishPackage(
        episode_id=spec.episode_id,
        video_uri=video_uri,
        title={lang: c.title for lang, c in by_lang.items()},
        description={lang: c.description for lang, c in by_lang.items()},
        tags={lang: c.tags for lang, c in by_lang.items()},
        chapters=[Chapter(start_s=s.start_s, title=s.template.replace("_", " ").capitalize()) for s in props.scenes],
        thumbnail_text=copy.thumbnail_text,
        made_for_kids=config.audience.made_for_kids,
        contains_synthetic_media=True,  # every voice and image is generated
        publish_at=spec.publish_slot,
    )
