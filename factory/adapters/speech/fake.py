"""Fake speech: a sine tone as long as the line would take to say at the requested rate. No network."""

import hashlib
import math
import struct
import wave
from pathlib import Path

from factory.adapters.speech.base import SpeechRequest, SpeechResult, check_rate, voices_hash
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


class FakeSpeech:
    rate_range = (0.25, 4.0)

    def __init__(self, pack: LanguagePack, voices: dict[str, str], sample_rate: int = SAMPLE_RATE):
        self.pack, self.voices, self.sample_rate = pack, voices, sample_rate
        self.identity = f"fake_speech/sine-tone-1@{sample_rate}#{voices_hash(voices)}"

    def seconds(self, text: str, rate: float) -> float:
        units, pack_rate = self.pack.speech_units(text), rate * self.pack.native_rate
        per_minute = self.pack.rate_unit in ("wpm", "chars_min")
        return max(MIN_SECONDS, units / pack_rate * 60 if per_minute else units / pack_rate)

    def synthesize(self, request: SpeechRequest, out_path: Path) -> SpeechResult:
        check_rate(request.rate, self.rate_range, "fake speech")
        seconds = self.seconds(request.text, request.rate)
        duration = write_tone(out_path, seconds, tone_hz(self.voices[request.voice]), self.sample_rate)
        return SpeechResult(duration_s=duration, words=None, charges=[])
