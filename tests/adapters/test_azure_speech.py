"""Azure Speech against a stand-in SDK; the `live` test calls the real service when a key is set."""

import io
import os
import wave
from datetime import timedelta
from types import SimpleNamespace

import pytest

from factory.adapters import media
from factory.adapters.costs import MediaPrice
from factory.adapters.speech.azure_speech import AzureSpeech, RateLimiter, retry_after, ssml, voice_locale
from factory.adapters.speech.base import SpeechError, SpeechRequest
from factory.tools.language_pack import load_pack
from tests.adapters.conformance import check_speech

VOICES = {"en-gb-female-1": "en-GB-SoniaNeural", "en-gb-male-1": "en-GB-RyanNeural"}


def wav_bytes(seconds: float, sample_rate: int = 24_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * round(seconds * sample_rate))
    return buf.getvalue()


class FakeSDK:
    """Just enough of azure.cognitiveservices.speech to drive AzureSpeech: replays scripted results."""

    ResultReason = SimpleNamespace(SynthesizingAudioCompleted="completed", Canceled="canceled")
    CancellationErrorCode = SimpleNamespace(TooManyRequests="TooManyRequests", AuthenticationFailure="AuthFailure")
    SpeechSynthesisBoundaryType = SimpleNamespace(Word="word", Punctuation="punct", Sentence="sentence")
    SpeechSynthesisOutputFormat = SimpleNamespace(Riff24Khz16BitMonoPcm="riff24", Riff16Khz16BitMonoPcm="riff16",
                                                  Riff48Khz16BitMonoPcm="riff48")

    def __init__(self, outcomes):
        self.outcomes, self.ssml, self.configs = list(outcomes), [], []
        sdk = self

        class SpeechConfig:
            def __init__(self, subscription, region):
                self.subscription, self.region, self.format = subscription, region, None
                sdk.configs.append(self)

            def set_speech_synthesis_output_format(self, fmt):
                self.format = fmt

        class Signal:
            def __init__(self):
                self.handlers = []

            def connect(self, handler):
                self.handlers.append(handler)

        class SpeechSynthesizer:
            def __init__(self, speech_config, audio_config):
                assert audio_config is None
                self.synthesis_word_boundary = Signal()

            def speak_ssml_async(self, markup):
                sdk.ssml.append(markup)
                result, events = sdk.outcomes.pop(0)
                for event in events:
                    for handler in self.synthesis_word_boundary.handlers:
                        handler(event)
                return SimpleNamespace(get=lambda: result)

        self.SpeechConfig, self.SpeechSynthesizer = SpeechConfig, SpeechSynthesizer


def completed(seconds: float, words=()):
    result = SimpleNamespace(reason="completed", audio_data=wav_bytes(seconds),
                             audio_duration=timedelta(seconds=seconds), cancellation_details=None)
    events = [SimpleNamespace(text=text, audio_offset=round(start * 1e7), duration=timedelta(seconds=length),
                              boundary_type=kind) for text, start, length, kind in words]
    return result, events


def canceled(code: str, details: str):
    return SimpleNamespace(reason="canceled", cancellation_details=SimpleNamespace(
        reason="Error", error_code=code, error_details=details)), []


def azure(outcomes, sleeps=None, **kwargs) -> tuple[AzureSpeech, FakeSDK]:
    sdk = FakeSDK(outcomes)
    sleeps = [] if sleeps is None else sleeps
    speech = AzureSpeech(key="k", region="westeurope", voices=VOICES, sdk=sdk, sleep=sleeps.append, **kwargs)
    return speech, sdk


REQUEST = SpeechRequest(text="Hi, Ben!", language="en", voice="en-gb-female-1", rate=0.8)


def test_ssml_sets_the_voice_locale_clamps_the_rate_and_escapes_the_text():
    markup = ssml('Tom & "Jerry" <3', "en-GB-SoniaNeural", 0.2)
    assert 'xml:lang="en-GB"' in markup and '<voice name="en-GB-SoniaNeural">' in markup
    assert '<prosody rate="0.50">Tom &amp; "Jerry" &lt;3</prosody>' in markup
    assert '<prosody rate="2.00">' in ssml("x", "en-GB-RyanNeural", 3.7)


def test_the_locale_comes_from_the_voice_name():
    assert voice_locale("en-GB-SoniaNeural") == "en-GB"
    assert voice_locale("zh-HK-HiuMaanNeural") == "zh-HK"
    assert voice_locale("en-US-Andrew:DragonHDLatestNeural") == "en-US"
    with pytest.raises(SpeechError, match="locale"):
        voice_locale("Sonia")


def test_a_line_is_written_with_word_timings_and_charged_per_character(tmp_path):
    words = [("Hi", 0.05, 0.3, "word"), (",", 0.35, 0.0, "punct"), ("Ben", 0.5, 0.4, "word")]
    speech, sdk = azure([completed(1.2, words)], price=MediaPrice(usd=16.0, per=1_000_000))
    result = check_speech(speech, REQUEST, tmp_path / "line.wav")
    assert sdk.configs[0].format == "riff24" and sdk.configs[0].region == "westeurope"
    assert '<prosody rate="0.80">Hi, Ben!</prosody>' in sdk.ssml[0]
    assert result.duration_s == 1.2
    assert [(w.text, w.start_s, w.end_s) for w in result.words] == [("Hi", 0.05, 0.35), ("Ben", 0.5, 0.9)]
    assert [(c.vendor, c.model, c.usd, c.priced) for c in result.charges] == [
        ("azure-speech", "en-GB-SoniaNeural", 0.000128, True)]


def test_no_word_boundary_events_means_no_word_timing(tmp_path):
    speech, _ = azure([completed(0.8)])
    result = speech.synthesize(REQUEST, tmp_path / "line.wav")
    assert result.words is None and result.charges[0].priced is False


def test_throttling_waits_as_told_and_retries(tmp_path):
    sleeps = []
    speech, sdk = azure([canceled("TooManyRequests", "429 Retry-After: 7"),
                         canceled("TooManyRequests", "too many requests"), completed(0.5)], sleeps)
    assert speech.synthesize(REQUEST, tmp_path / "line.wav").duration_s == 0.5
    assert sleeps == [7.0, 10.0] and len(sdk.ssml) == 3


def test_throttling_gives_up_after_three_retries(tmp_path):
    speech, sdk = azure([canceled("TooManyRequests", "slow down")] * 4)
    with pytest.raises(SpeechError, match="TooManyRequests"):
        speech.synthesize(REQUEST, tmp_path / "line.wav")
    assert len(sdk.ssml) == 4


def test_a_canceled_request_names_the_reason(tmp_path):
    speech, sdk = azure([canceled("AuthFailure", "invalid subscription key")])
    with pytest.raises(SpeechError, match="en-GB-SoniaNeural: AuthFailure: invalid subscription key"):
        speech.synthesize(REQUEST, tmp_path / "line.wav")
    assert len(sdk.ssml) == 1


def test_identity_changes_with_the_voices_and_sample_rate():
    a, _ = azure([])
    b = AzureSpeech(key="k", region="r", voices={**VOICES, "en-gb-male-1": "en-GB-ThomasNeural"}, sdk=FakeSDK([]))
    c = AzureSpeech(key="k", region="r", voices=VOICES, sample_rate=16_000, sdk=FakeSDK([]))
    assert len({a.identity, b.identity, c.identity}) == 3
    with pytest.raises(SpeechError, match="22050 Hz"):
        AzureSpeech(key="k", region="r", voices=VOICES, sample_rate=22_050, sdk=FakeSDK([]))


def test_the_rate_limiter_spaces_calls_to_the_per_minute_limit():
    now, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(2, clock=lambda: now[0], sleep=sleep)
    for at in (0.0, 10.0, 15.0, 80.0):
        now[0] = max(now[0], at)
        limiter.wait()
    assert sleeps == [45.0]


def test_retry_after_reads_the_header_or_falls_back():
    assert retry_after("Status 429, Retry-After: 12") == 12.0
    assert retry_after("") == 10.0


def test_the_live_profile_maps_every_en_voice(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "westeurope")
    speech = media.speech_for("live", load_pack("en"))
    assert speech.voices == VOICES and speech.limiter.per_minute == 20
    assert speech.price == MediaPrice(usd=16.0, per=1_000_000)


@pytest.mark.live
def test_live_azure_speech_passes_conformance(tmp_path):
    if not os.environ.get("AZURE_SPEECH_KEY"):
        pytest.skip("AZURE_SPEECH_KEY is not set")
    speech = media.speech_for("live", load_pack("en"))
    result = check_speech(speech, SpeechRequest(text="Where is the station, please?", language="en",
                                                voice="en-gb-female-1", rate=0.8), tmp_path / "line.wav")
    print(f"duration {result.duration_s:.2f}s, words {len(result.words or [])}, charges {result.charges}")
