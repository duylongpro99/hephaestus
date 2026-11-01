"""A6 Voice Director and C4/C5 voicing (architecture §7).

A6 is a deterministic stand-in here: each cast member gets the pack voice the Channel Bible names,
or one in cast order, and each line the band's rate for its segment speed. C4 synthesizes every
line through the speech synthesizer; C5 joins the lines with their scripted pauses into one
master track.
"""

import wave
from pathlib import Path
from typing import Callable

from factory.adapters.costs import Charge, MediaError, ledger_entries
from factory.adapters.speech.base import SpeechRequest, SpeechSynthesizer
from factory.artifacts import safe_name
from factory.config import ResolvedConfig
from factory.contracts import AudioManifest, LineAudio, LineDirective, Script, VoiceDirectives
from factory.tools.language_pack import LanguagePack, VoiceSpec

STATION = "c4_tts"  # the station its synthesis costs are recorded under


def cast_voices(config: ResolvedConfig, pack: LanguagePack) -> dict[str, VoiceSpec]:
    if not pack.voices:
        raise ValueError(f"pack {pack.code} offers no voices to cast")
    by_key = {v.key: v for v in pack.voices}
    return {m.id: by_key[m.voice] if m.voice else pack.voices[i % len(pack.voices)]
            for i, m in enumerate(config.channel.cast)}


def direct(script: Script, config: ResolvedConfig, pack: LanguagePack) -> VoiceDirectives:
    voices, rate = cast_voices(config, pack), config.band.rate
    lines = []
    for segment in script.segments:
        slow = segment.speed == "slow"
        for line in segment.lines:
            voice = voices[line.speaker]
            lines.append(LineDirective(
                line_id=line.id, speaker=line.speaker, voice=voice.key,
                style_tags=list(voice.tags), rate=rate.min if slow else rate.midpoint, rate_unit=rate.unit,
                pause_ms=line.pause_after_ms, variant="slow" if slow else "natural",
            ))
    return VoiceDirectives(episode_id=script.episode_id, lines=lines)


def assemble(parts: list[tuple[Path, float]], out_path: Path) -> int:
    """Join mono WAVs, each followed by `pause_s` of silence, into `out_path`; return the sample rate."""
    params, frames = None, []
    for path, pause_s in parts:
        with wave.open(str(path), "rb") as wav:
            if params is None:
                params = wav.getparams()
            elif wav.getparams()[:3] != params[:3]:
                raise ValueError(f"{path.name} has a different channel count, sample width or rate")
            frames.append(wav.readframes(wav.getnframes()))
        frames.append(b"\x00" * params.sampwidth * params.nchannels * round(pause_s * params.framerate))
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(b"".join(frames))
    return params.framerate


def voice(
    script: Script, directives: VoiceDirectives, pack: LanguagePack, speech: SpeechSynthesizer, media_dir: Path,
    uri_of: Callable[[Path], str],
) -> tuple[AudioManifest, list[Charge]]:
    """The audio manifest, and what the synthesizer charged for it."""
    text = {line.id: line.text for line in script.iter_lines()}
    lines_dir = media_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)
    entries, parts, charges, start = [], [], [], 0.0
    for d in directives.lines:
        path = lines_dir / f"{safe_name(d.line_id)}.wav"
        request = SpeechRequest(text=text[d.line_id], language=pack.code, voice=d.voice, rate=d.rate / pack.native_rate)
        try:
            result = speech.synthesize(request, path)
        except MediaError as exc:
            exc.costs = ledger_entries(STATION, charges)
            raise
        duration, pause = result.duration_s, d.pause_ms / 1000
        charges.extend(result.charges)
        entries.append(LineAudio(line_id=d.line_id, uri=uri_of(path), start_s=round(start, 4),
                                 duration_s=round(duration, 4), pause_after_s=pause, words=result.words or []))
        parts.append((path, pause))
        start += duration + pause
    master = media_dir / "master.wav"
    sample_rate = assemble(parts, master)
    manifest = AudioManifest(episode_id=script.episode_id, lines=entries, master_uri=uri_of(master),
                             sample_rate=sample_rate, total_duration_s=round(start, 4))
    return manifest, charges
