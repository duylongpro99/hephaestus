"""A6 Voice Director and C4/C5 voicing (architecture §7).

A6 is a deterministic stand-in here: each cast member gets the pack voice the Channel Bible names,
or one in cast order, and each line the band's rate for its segment speed. C4 synthesizes every
line through the speech synthesizer; C5 joins the lines with their scripted pauses into one
master track.
"""

import hashlib
import json
import os
import wave
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable

from factory.adapters.costs import Charge, MediaError, ledger_entries
from factory.adapters.speech.base import SpeechError, SpeechRequest, SpeechResult, SpeechSynthesizer
from factory.artifacts import safe_name
from factory.config import ResolvedConfig
from factory.contracts import AudioManifest, LineAudio, LineDirective, Script, VoiceDirectives, WordTiming
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


class RateOutOfRange(SpeechError):
    """A line asks for a rate the synthesizer cannot speak at: a config error, so retrying will not help."""


def line_key(speech: SpeechSynthesizer, request: SpeechRequest) -> str:
    """Everything that decides a line's audio; equal keys mean an identical WAV."""
    payload = [speech.identity, request.text, request.language, request.voice, request.rate]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def line_paths(lines_dir: Path, line_id: str, key: str) -> tuple[Path, Path]:
    stem = f"{safe_name(line_id)}.{key[:12]}"
    return lines_dir / f"{stem}.wav", lines_dir / f"{stem}.json"


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def load_line(wav_path: Path, sidecar: Path, key: str) -> SpeechResult | None:
    """A line an earlier attempt finished: its sidecar matches `key` and its WAV has the recorded length."""
    try:
        done = json.loads(sidecar.read_text(encoding="utf-8"))
        if done.get("key") != key:
            return None
        with wave.open(str(wav_path)) as wav:
            # Count the frames actually on disk: a truncated file keeps the header's original frame count.
            frame_size, framerate = wav.getsampwidth() * wav.getnchannels(), wav.getframerate()
            frames = len(wav.readframes(wav.getnframes())) // frame_size
        duration = float(done["duration_s"])
        if abs(frames - duration * framerate) > 1:
            return None
        words = [WordTiming.model_validate(w) for w in done["words"]] if done["words"] is not None else None
        return SpeechResult(duration_s=duration, words=words, charges=[Charge(**c) for c in done["charges"]])
    except (OSError, ValueError, KeyError, TypeError, wave.Error, EOFError):
        return None


def store_line(
    speech: SpeechSynthesizer, request: SpeechRequest, wav_path: Path, sidecar: Path, key: str,
) -> SpeechResult:
    """Synthesize to a temporary file, move it into place, then write the sidecar that marks the line done."""
    tmp = wav_path.with_name(f".{wav_path.name}.{os.getpid()}.tmp")
    try:
        result = speech.synthesize(request, tmp)
        os.replace(tmp, wav_path)
    finally:
        tmp.unlink(missing_ok=True)
    done = {"key": key, "duration_s": result.duration_s,
            "words": [w.model_dump(mode="json") for w in result.words] if result.words is not None else None,
            "charges": [asdict(c) for c in result.charges]}
    write_atomic(sidecar, json.dumps(done, ensure_ascii=False, indent=2).encode())
    return result


def check_rates(requests: list[tuple[LineDirective, SpeechRequest]], speech: SpeechSynthesizer) -> None:
    low, high = speech.rate_range
    bad = [f"{d.line_id} at {r.rate:.2f}" for d, r in requests if not low <= r.rate <= high]
    if bad:
        raise RateOutOfRange(f"{len(bad)} line(s) ask for a rate outside the synthesizer's {low:.2f}-{high:.2f} "
                             f"({', '.join(bad)}); check the level band's speaking rate and the pack's native rate")


def voice(
    script: Script, directives: VoiceDirectives, pack: LanguagePack, speech: SpeechSynthesizer, media_dir: Path,
    uri_of: Callable[[Path], str],
) -> tuple[AudioManifest, list[Charge]]:
    """The audio manifest, and what the synthesizer charged for every line in it.

    Each line is stored under a key of everything that decides its audio, with a sidecar written last as
    the mark that it is done. A retry of the station writes into the same media directory, so it reuses
    the lines an earlier attempt finished and only calls the provider for the rest. Each line's charge
    carries a dedupe key of the line and its audio key, so the ledger records it once whether it arrives
    with a failed attempt's costs, with the finished artifact, or both, while two lines with the same text
    (a repeated drill phrase) are two syntheses and two charges. Two real syntheses with the same key in the same directory (an
    operator deleting a WAV by hand) are charged once: the ledger stays a floor, as it is for unpriced models.
    """
    text = {line.id: line.text for line in script.iter_lines()}
    requests = [(d, SpeechRequest(text=text[d.line_id], language=pack.code, voice=d.voice,
                                  rate=d.rate / pack.native_rate)) for d in directives.lines]
    check_rates(requests, speech)
    lines_dir = media_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)
    entries, parts, charges, start = [], [], [], 0.0
    for d, request in requests:
        key = line_key(speech, request)
        path, sidecar = line_paths(lines_dir, d.line_id, key)
        result = load_line(path, sidecar, key)
        if result is None:
            path.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            try:
                result = store_line(speech, request, path, sidecar, key)
            except MediaError as exc:
                exc.costs = ledger_entries(STATION, charges)
                raise
        dedupe_key = f"{STATION}:{media_dir.name}:{safe_name(d.line_id)}:{key}"
        charges.extend(replace(c, dedupe_key=dedupe_key) for c in result.charges)
        duration, pause = result.duration_s, d.pause_ms / 1000
        entries.append(LineAudio(line_id=d.line_id, uri=uri_of(path), start_s=round(start, 4),
                                 duration_s=round(duration, 4), pause_after_s=pause, words=result.words or []))
        parts.append((path, pause))
        start += duration + pause
    master = media_dir / "master.wav"
    sample_rate = assemble(parts, master)
    manifest = AudioManifest(episode_id=script.episode_id, lines=entries, master_uri=uri_of(master),
                             sample_rate=sample_rate, total_duration_s=round(start, 4))
    return manifest, charges
