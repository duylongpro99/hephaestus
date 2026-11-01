"""Azure AI Speech: neural voices over the Speech SDK, with per-word timing from WordBoundary events."""

import re
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from factory.adapters.costs import MediaPrice, charge
from factory.adapters.speech.base import SpeechError, SpeechRequest, SpeechResult, voices_hash
from factory.contracts import WordTiming

TICKS_PER_SECOND = 10_000_000  # SDK offsets and durations are in 100 ns units
MIN_RATE, MAX_RATE = 0.5, 2.0
RETRIES = 3
DEFAULT_RETRY_AFTER_S = 10.0
SAMPLE_RATE_FORMATS = {16_000: "Riff16Khz16BitMonoPcm", 24_000: "Riff24Khz16BitMonoPcm",
                       48_000: "Riff48Khz16BitMonoPcm"}


def voice_locale(voice_id: str) -> str:
    """The locale a neural voice name starts with: "en-GB-SoniaNeural" -> "en-GB"."""
    match = re.match(r"([a-z]{2,3}-[A-Za-z]{2,4}(?:-[A-Za-z]+)?)-[A-Z]", voice_id)
    if not match:
        raise SpeechError(f"cannot tell the locale of Azure voice {voice_id!r}; expected e.g. en-GB-SoniaNeural")
    return match.group(1)


def ssml(text: str, voice_id: str, rate: float) -> str:
    rate = min(MAX_RATE, max(MIN_RATE, rate))
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang={quoteattr(voice_locale(voice_id))}>'
            f"<voice name={quoteattr(voice_id)}><prosody rate=\"{rate:.2f}\">{escape(text)}</prosody></voice></speak>")


def retry_after(details: str) -> float:
    """Seconds to wait from a throttling error's details; the SDK passes the header through as text."""
    match = re.search(r"retry-after\D{0,4}(\d+(?:\.\d+)?)", details or "", re.IGNORECASE)
    return float(match.group(1)) if match else DEFAULT_RETRY_AFTER_S


class RateLimiter:
    """At most `per_minute` calls in any 60 s window; `None` means no limit."""

    def __init__(self, per_minute: int | None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.per_minute, self.clock, self.sleep = per_minute, clock, sleep
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        if not self.per_minute:
            return
        with self.lock:
            now = self.clock()
            while self.calls and now - self.calls[0] >= 60:
                self.calls.popleft()
            if len(self.calls) >= self.per_minute:
                self.sleep(60 - (now - self.calls[0]))
                self.calls.popleft()
                now = self.clock()
            self.calls.append(now)


class AzureSpeech:
    def __init__(self, *, key: str, region: str, voices: dict[str, str], sample_rate: int = 24_000,
                 price: MediaPrice | None = None, max_requests_per_minute: int | None = None,
                 name: str = "azure-speech", sdk=None, sleep: Callable[[float], None] = time.sleep):
        if sample_rate not in SAMPLE_RATE_FORMATS:
            raise SpeechError(f"Azure Speech has no mono PCM output at {sample_rate} Hz; "
                              f"use one of {', '.join(map(str, SAMPLE_RATE_FORMATS))}")
        for voice_id in voices.values():
            voice_locale(voice_id)
        if sdk is None:
            import azure.cognitiveservices.speech as sdk
        self.sdk, self.voices, self.sample_rate, self.price, self.name = sdk, voices, sample_rate, price, name
        self.sleep = sleep
        self.limiter = RateLimiter(max_requests_per_minute, sleep=sleep)
        self.config = sdk.SpeechConfig(subscription=key, region=region)
        self.config.set_speech_synthesis_output_format(
            getattr(sdk.SpeechSynthesisOutputFormat, SAMPLE_RATE_FORMATS[sample_rate]))
        self.identity = f"azure_speech/neural@{sample_rate}#{voices_hash(voices)}"

    def synthesize(self, request: SpeechRequest, out_path: Path) -> SpeechResult:
        voice_id = self.voices.get(request.voice)
        if voice_id is None:
            raise SpeechError(f"no Azure voice mapped for {request.voice}")
        markup = ssml(request.text, voice_id, request.rate)
        for attempt in range(RETRIES + 1):
            self.limiter.wait()
            result, events = self.speak(markup)
            if result.reason == self.sdk.ResultReason.SynthesizingAudioCompleted:
                break
            details = result.cancellation_details
            throttled = getattr(details, "error_code", None) == self.sdk.CancellationErrorCode.TooManyRequests
            if throttled and attempt < RETRIES:
                self.sleep(retry_after(details.error_details))
                continue
            reason = f"{details.error_code}: {details.error_details}" if details else str(result.reason)
            raise SpeechError(f"Azure Speech failed for voice {voice_id}: {reason}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(result.audio_data)
        duration = result.audio_duration.total_seconds()
        words = [WordTiming(text=e.text, start_s=round(e.audio_offset / TICKS_PER_SECOND, 4),
                            end_s=round(min(duration, (e.audio_offset + ticks(e.duration)) / TICKS_PER_SECOND), 4))
                 for e in events if e.boundary_type == self.sdk.SpeechSynthesisBoundaryType.Word]
        return SpeechResult(duration_s=duration, words=words or None,
                            charges=[charge(self.name, voice_id, len(request.text), self.price)])

    def speak(self, markup: str):
        synthesizer = self.sdk.SpeechSynthesizer(speech_config=self.config, audio_config=None)
        events = []
        synthesizer.synthesis_word_boundary.connect(events.append)
        return synthesizer.speak_ssml_async(markup).get(), events


def ticks(duration) -> int:
    """WordBoundary durations arrive as a timedelta in recent SDKs and as ticks in older ones."""
    return round(duration.total_seconds() * TICKS_PER_SECOND) if hasattr(duration, "total_seconds") else duration
