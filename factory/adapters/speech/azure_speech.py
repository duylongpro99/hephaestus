"""Azure AI Speech: neural voices over the Speech SDK, with per-word timing from WordBoundary events."""

import re
import threading
import time
import wave
from collections import deque
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from factory.adapters.costs import MediaPrice, billed_chars, charge
from factory.adapters.speech.base import (
    SpeechError,
    SpeechRequest,
    SpeechResult,
    check_rate,
    voices_hash,
)
from factory.contracts import WordTiming

TICKS_PER_SECOND = 10_000_000  # SDK offsets and durations are in 100 ns units
RATE_RANGE = (0.5, 2.0)  # what <prosody rate> accepts as a multiplier
RETRIES = 3  # retries after the first attempt, shared by throttling and transient failures
DEFAULT_RETRY_AFTER_S = 10.0
BACKOFF_BASE_S, BACKOFF_MAX_S = 2.0, 30.0
# Cancellations worth another attempt: the service or the network hiccupped, the request itself was fine.
# ServiceError is left out on purpose: it can be permanent, and retrying a paid request blindly costs money.
TRANSIENT_ERRORS = ("ServiceTimeout", "ConnectionFailure", "ServiceUnavailable")
SAMPLE_RATE_FORMATS = {16_000: "Riff16Khz16BitMonoPcm", 24_000: "Riff24Khz16BitMonoPcm",
                       48_000: "Riff48Khz16BitMonoPcm"}


def voice_locale(voice_id: str) -> str:
    """The locale a neural voice name starts with: "en-GB-SoniaNeural" -> "en-GB"."""
    match = re.match(r"([a-z]{2,3}-[A-Za-z]{2,4}(?:-[A-Za-z]+)?)-[A-Z]", voice_id)
    if not match:
        raise SpeechError(f"cannot tell the locale of Azure voice {voice_id!r}; expected e.g. en-GB-SoniaNeural")
    return match.group(1)


def ssml(text: str, voice_id: str, rate: float) -> str:
    check_rate(rate, RATE_RANGE, "Azure Speech")
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang={quoteattr(voice_locale(voice_id))}>'
            f"<voice name={quoteattr(voice_id)}><prosody rate=\"{rate:.2f}\">{escape(text)}</prosody></voice></speak>")


def retry_after(details: str) -> float:
    """Seconds to wait from a throttling error's details; the SDK passes the header through as text."""
    match = re.search(r"retry-after\D{0,4}(\d+(?:\.\d+)?)", details or "", re.IGNORECASE)
    return float(match.group(1)) if match else DEFAULT_RETRY_AFTER_S


def backoff_s(attempt: int) -> float:
    """Exponential wait before retry number `attempt + 1` after a transient failure: 2, 4, 8 s, capped."""
    return min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** attempt)


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
    rate_range = RATE_RANGE

    def __init__(self, *, key: str, region: str, voices: dict[str, str], sample_rate: int = 24_000,
                 price: MediaPrice | None = None, max_requests_per_minute: int | None = None,
                 wide_char_units: int = 1, name: str = "azure-speech", sdk=None,
                 sleep: Callable[[float], None] = time.sleep):
        if sample_rate not in SAMPLE_RATE_FORMATS:
            raise SpeechError(f"Azure Speech has no mono PCM output at {sample_rate} Hz; "
                              f"use one of {', '.join(map(str, SAMPLE_RATE_FORMATS))}")
        for voice_id in voices.values():
            voice_locale(voice_id)
        if sdk is None:
            import azure.cognitiveservices.speech as sdk
        self.sdk, self.voices, self.sample_rate, self.price, self.name = sdk, voices, sample_rate, price, name
        self.sleep, self.wide_char_units = sleep, wide_char_units
        codes = sdk.CancellationErrorCode
        self.throttled = getattr(codes, "TooManyRequests", None)
        self.transient = {getattr(codes, name) for name in TRANSIENT_ERRORS if hasattr(codes, name)}
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
            code = getattr(details, "error_code", None)
            reason = f"{details.error_code}: {details.error_details}" if details else str(result.reason)
            if code == self.throttled and attempt < RETRIES:
                self.sleep(retry_after(details.error_details))
            elif code in self.transient and attempt < RETRIES:
                self.sleep(backoff_s(attempt))
            elif code == self.throttled or code in self.transient:
                raise SpeechError(f"Azure Speech failed for voice {voice_id} after {attempt + 1} attempts: {reason}")
            else:
                raise SpeechError(f"Azure Speech failed for voice {voice_id}: {reason}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(result.audio_data)
        duration = self.wav_seconds(out_path)
        words = [WordTiming(text=e.text, start_s=round(e.audio_offset / TICKS_PER_SECOND, 4),
                            end_s=round(min(duration, (e.audio_offset + ticks(e.duration)) / TICKS_PER_SECOND), 4))
                 for e in events if e.boundary_type == self.sdk.SpeechSynthesisBoundaryType.Word]
        return SpeechResult(duration_s=duration, words=words or None,
                            charges=[charge(self.name, voice_id, billed_chars(request.text, self.wide_char_units),
                                            self.price)])

    def wav_seconds(self, path: Path) -> float:
        """The line's length from the frames actually written, not the duration the service reports."""
        try:
            with wave.open(str(path)) as wav:
                shape = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                # Count the frames on disk, as a reused line does: a header can claim more than was sent.
                frames = len(wav.readframes(wav.getnframes())) // max(1, shape[0] * shape[1])
        except (wave.Error, EOFError) as exc:
            raise SpeechError(f"Azure Speech returned audio that is not a WAV: {exc}") from exc
        if shape != (1, 2, self.sample_rate):
            raise SpeechError(f"Azure Speech returned {shape[0]} channel(s), {8 * shape[1]}-bit at {shape[2]} Hz; "
                              f"expected mono 16-bit at {self.sample_rate} Hz")
        return frames / self.sample_rate

    def speak(self, markup: str):
        synthesizer = self.sdk.SpeechSynthesizer(speech_config=self.config, audio_config=None)
        events = []
        synthesizer.synthesis_word_boundary.connect(events.append)
        return synthesizer.speak_ssml_async(markup).get(), events


def ticks(duration) -> int:
    """WordBoundary durations arrive as a timedelta in recent SDKs and as ticks in older ones."""
    return round(duration.total_seconds() * TICKS_PER_SECOND) if hasattr(duration, "total_seconds") else duration
