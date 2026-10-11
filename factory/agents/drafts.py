"""LLM-facing script schema, built per channel from its support languages.

Structured outputs only accept closed objects, so the contract's `dict[str, str]` translation
and gloss maps become one field per language (`translation_vi`, `gloss_en`, ...). `to_script`
converts a draft back into the `Script` contract.
"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model

from factory.contracts import Script
from factory.contracts.script import SegmentType


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


def translation_languages(target: str, support: list[str]) -> list[str]:
    """Languages that get a full line translation: every support language except the target."""
    return [lang for lang in support if lang != target]


@lru_cache
def draft_models(target: str, support: tuple[str, ...]) -> type[BaseModel]:
    translations = translation_languages(target, list(support))
    line_fields = {f"translation_{lang}": (str, ...) for lang in translations}
    DraftLine = create_model(
        "DraftLine", __base__=_Closed,
        id=(str, ...), speaker=(str, ...), text=(str, ...), pause_after_ms=(int, ...),
        visual_cue=(str | None, ...), **line_fields,
    )
    DraftQuizItem = create_model(
        "DraftQuizItem", __base__=_Closed,
        id=(str, ...), question=(str, ...), options=(list[str], ...), answer_index=(int, ...), **line_fields,
    )
    DraftSegment = create_model(
        "DraftSegment", __base__=_Closed,
        id=(str, ...), type=(SegmentType, ...), speed=(Literal["slow", "natural"] | None, ...),
        layout=(str | None, ...), lines=(list[DraftLine], ...), items=(list[DraftQuizItem], ...),
    )
    gloss_fields = {f"gloss_{lang}": (str, ...) for lang in support}
    DraftVocab = create_model(
        "DraftVocab", __base__=_Closed, word=(str, ...), is_target=(bool, ...), **gloss_fields,
    )
    return create_model(
        "DraftScript", __base__=_Closed,
        title_working=(str, ...), hook=(str, ...), segments=(list[DraftSegment], ...),
        vocab=(list[DraftVocab], ...), grammar_notes=(list[str], ...), interaction_prompts=(list[str], ...),
    )


def _pick(data: dict, prefix: str, languages: list[str]) -> dict[str, str]:
    return {lang: data.pop(f"{prefix}_{lang}") for lang in languages if f"{prefix}_{lang}" in data}


def to_script(draft: BaseModel, episode_id: str, target: str, support: list[str]) -> Script:
    translations = translation_languages(target, support)
    data = draft.model_dump()
    for segment in data["segments"]:
        for entry in [*segment["lines"], *segment["items"]]:
            entry["translation"] = _pick(entry, "translation", translations)
    for item in data["vocab"]:
        item["gloss"] = _pick(item, "gloss", support)
    return Script.model_validate({"episode_id": episode_id, **data})


def to_draft_dict(script: Script, target: str, support: list[str]) -> dict:
    """The inverse of `to_script`, used to show a script in draft shape (few-shot, editor)."""
    translations = translation_languages(target, support)
    data = script.model_dump(mode="json", exclude={"episode_id", "schema_version"})
    for segment in data["segments"]:
        for entry in [*segment["lines"], *segment["items"]]:
            tr = entry.pop("translation")
            entry.update({f"translation_{lang}": tr.get(lang, "") for lang in translations})
    for item in data["vocab"]:
        gloss = item.pop("gloss")
        item.update({f"gloss_{lang}": gloss.get(lang, "") for lang in support})
    return data
