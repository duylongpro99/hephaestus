"""Text-to-speech adapter interface (C4). Real vendors and the fake implement the same protocol."""

from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    vendor: str
    identity: str  # the vendor and model plus anything that changes the audio; part of the station_version

    def synthesize(self, text: str, voice: str, rate: float, out_path: Path) -> float:
        """Write a mono WAV of `text` spoken by `voice` at `rate` (pack rate unit); return its seconds."""
        ...
