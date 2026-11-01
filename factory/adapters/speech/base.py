"""Speech synthesis (C4): turn one scripted line into a WAV. Every provider implements this protocol."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.adapters.costs import Charge, MediaError
from factory.contracts import WordTiming


class SpeechError(MediaError):
    pass


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    language: str  # the pack's language code, e.g. "en"
    voice: str  # an abstract voice key of the pack, e.g. "en-gb-female-1"
    rate: float  # relative to the pack's native speaking rate; 1.0 = native


@dataclass
class SpeechResult:
    duration_s: float
    words: list[WordTiming] | None  # line-relative; None when the provider reports no word timing
    charges: list[Charge]


class SpeechSynthesizer(Protocol):
    identity: str  # everything that changes the audio; part of the station_version

    def synthesize(self, request: SpeechRequest, out_path: Path) -> SpeechResult:
        """Write a mono 16-bit PCM WAV of the line to `out_path`."""
        ...


def voices_hash(voices: dict[str, str]) -> str:
    """A short hash of the voice mapping, so a changed voice changes the synthesizer's identity."""
    return hashlib.sha256(json.dumps(voices, sort_keys=True).encode()).hexdigest()[:8]
