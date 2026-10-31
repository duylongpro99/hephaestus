"""Fake TTS: a sine tone as long as the line would take to say at the requested rate. No network."""

import hashlib
import math
import struct
import wave
from pathlib import Path

from factory.tools.language_pack import LanguagePack

SAMPLE_RATE = 24_000
MIN_SECONDS = 0.3


def tone_hz(voice: str) -> int:
    """A distinct pitch per voice, so two speakers are told apart by ear."""
    return 220 + int(hashlib.sha256(voice.encode()).hexdigest(), 16) % 8 * 55


def write_tone(out_path: Path, seconds: float, hz: int, sample_rate: int = SAMPLE_RATE) -> float:
    samples = max(1, round(seconds * sample_rate))
    frames = b"".join(
        struct.pack("<h", round(8000 * math.sin(2 * math.pi * hz * i / sample_rate))) for i in range(samples)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return samples / sample_rate


class FakeTTS:
    vendor = "fake"
    identity = "fake/sine-tone-1"

    def __init__(self, pack: LanguagePack):
        self.pack = pack

    def seconds(self, text: str, rate: float) -> float:
        units = self.pack.speech_units(text)
        per_minute = self.pack.rate_unit in ("wpm", "chars_min")
        return max(MIN_SECONDS, units / rate * 60 if per_minute else units / rate)

    def synthesize(self, text: str, voice: str, rate: float, out_path: Path) -> float:
        return write_tone(out_path, self.seconds(text, rate), tone_hz(voice))
