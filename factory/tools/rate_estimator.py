"""Estimate spoken duration from the Language Pack's speech units and the level's rate band."""

from factory.config import RateBand
from factory.contracts import Script
from factory.tools.language_pack import LanguagePack


def speech_units(script: Script, pack: LanguagePack) -> int:
    return sum(pack.speech_units(line.text) for line in script.iter_lines())


def estimate_duration_min(script: Script, pack: LanguagePack, rate: RateBand) -> float:
    """Speech units at the band midpoint, plus every scripted pause."""
    if rate.unit != pack.rate_unit:
        raise ValueError(f"rate band unit {rate.unit} does not match pack unit {pack.rate_unit}")
    units = speech_units(script, pack)
    if rate.unit in ("wpm", "chars_min"):  # units per minute
        speaking_min = units / rate.midpoint
    else:  # syllables_s, mora_s: units per second
        speaking_min = units / rate.midpoint / 60
    pauses_min = sum(line.pause_after_ms for line in script.iter_lines()) / 60_000
    return round(speaking_min + pauses_min, 2)


def duration_within(duration_min: float, length_min: tuple[float, float]) -> bool:
    low, high = length_min
    return low <= duration_min <= high
