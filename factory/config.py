"""Merge the configuration layers into one ResolvedConfig (architecture §4.0 and §4.5).

Layers are merged in order: Language Pack, Level Framework, Audience Profile, Channel Bible.
A later layer overrides an earlier one: the band comes from the framework, then the
audience's `band_overrides`, then the channel's `band_overrides`.
"""

import copy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"


class _Layer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RateBand(_Layer):
    unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    min: float
    max: float

    @property
    def midpoint(self) -> float:
        return (self.min + self.max) / 2


class LevelBand(_Layer):
    coverage_min: float
    new_word_max: float
    target_repetition_min: int
    sentence_length: tuple[int, int]
    long_sentence_share_max: float
    sentence_length_gate: Literal["band", "ceiling"] = "band"
    rate: RateBand
    pause_ms: tuple[int, int]
    grammar: list[str] = []


class PackSummary(_Layer):
    code: str
    script_direction: Literal["ltr", "rtl"]
    rate_unit: Literal["wpm", "syllables_s", "mora_s", "chars_min"]
    native_rate: float


class AudienceProfile(_Layer):
    profile: str
    version: int
    ages: tuple[int, int | None]
    made_for_kids: bool
    rate_multiplier: float
    length_min: tuple[float, float]
    formats: list[str]
    band_overrides: dict[str, Any] = {}


class Persona(_Layer):
    name: str
    bio: str
    speaking_style: str
    catchphrases: list[str] = []


class CastMember(_Layer):
    id: str
    role: str
    description: str


class ChannelTarget(_Layer):
    pack: str
    framework: str
    levels: list[str]


class ChannelBible(_Layer):
    channel: str
    version: int
    target: ChannelTarget
    audience: str
    support_languages: list[str]
    persona: Persona
    cast: list[CastMember]
    formats: list[str]
    band_overrides: dict[str, Any] = {}


class ResolvedConfig(_Layer):
    pack: PackSummary
    framework: str
    framework_version: int
    level: str
    band: LevelBand
    audience: AudienceProfile
    channel: ChannelBible
    config_hash: str = ""

    @model_validator(mode="after")
    def _check(self):
        extra = set(self.channel.formats) - set(self.audience.formats)
        if extra:
            raise ValueError(f"channel formats {sorted(extra)} are not allowed for audience {self.audience.profile}")
        if self.band.rate.unit != self.pack.rate_unit:
            raise ValueError(f"band rate unit {self.band.rate.unit} != pack rate unit {self.pack.rate_unit}")
        return self

    def canonical_json(self) -> str:
        """Canonical JSON without the hash, used as the cached prompt prefix and hash input."""
        data = self.model_dump(mode="json", exclude={"config_hash"})
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def deep_merge(base: dict, override: dict) -> dict:
    """Return `base` with `override` applied; nested dicts merge, other values replace."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def compute_hash(config: ResolvedConfig) -> str:
    return "sha256:" + hashlib.sha256(config.canonical_json().encode("utf-8")).hexdigest()


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def pack_module(code: str):
    """The module of a pack; a code such as `xx-fixture` lives in the package `packs.xx_fixture`."""
    return importlib.import_module(f"packs.{code.replace('-', '_')}.pack")


def pack_summary(code: str) -> PackSummary:
    pack_cls = pack_module(code).Pack
    return PackSummary(
        code=pack_cls.code,
        script_direction=pack_cls.script_direction,
        rate_unit=pack_cls.rate_unit,
        native_rate=pack_cls.native_rate,
    )


def resolve_layers(
    pack: PackSummary, framework: dict, audience: dict, channel: dict, level: str
) -> ResolvedConfig:
    if level not in framework["bands"]:
        raise ValueError(f"level {level} has no band in framework {framework['framework']}")
    audience_profile = AudienceProfile.model_validate(audience)
    bible = ChannelBible.model_validate(channel)
    if level not in bible.target.levels:
        raise ValueError(f"channel {bible.channel} does not target level {level}")

    band = deep_merge(framework["bands"][level], audience_profile.band_overrides)
    band = deep_merge(band, bible.band_overrides)
    rate = band["rate"]
    band["rate"] = {**rate, "min": rate["min"] * audience_profile.rate_multiplier,
                    "max": rate["max"] * audience_profile.rate_multiplier}

    config = ResolvedConfig(
        pack=pack,
        framework=framework["framework"],
        framework_version=framework["version"],
        level=level,
        band=LevelBand.model_validate(band),
        audience=audience_profile,
        channel=bible,
    )
    config.config_hash = compute_hash(config)
    return config


def resolve(channel: str, level: str, config_dir: Path = CONFIG_DIR) -> ResolvedConfig:
    """Resolve the configuration for one channel and level from the files in `config_dir`."""
    bible = load_yaml(config_dir / "channels" / f"{channel}.yaml")
    framework = load_yaml(config_dir / "frameworks" / f"{bible['target']['framework']}.yaml")
    audience = load_yaml(config_dir / "audiences" / f"{bible['audience']}.yaml")
    return resolve_layers(pack_summary(bible["target"]["pack"]), framework, audience, bible, level)
