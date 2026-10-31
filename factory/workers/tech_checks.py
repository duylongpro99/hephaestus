"""C9 tech checks: ffprobe the rendered video against the audio it should carry (architecture §7)."""

from pathlib import Path

from factory.adapters import ffmpeg
from factory.contracts import AudioManifest, QAReport

REVIEWER = "c9_tech_checks"
DURATION_TOLERANCE = 0.05


def check(video: Path, audio: AudioManifest, width: int, height: int) -> QAReport:
    info = ffmpeg.probe(video)
    streams = {s["codec_type"]: s for s in reversed(info.get("streams", []))}
    failures = []
    v, a = streams.get("video"), streams.get("audio")
    if v is None:
        failures.append("no video stream")
    elif (v["width"], v["height"]) != (width, height):
        failures.append(f"video is {v['width']}x{v['height']}, expected {width}x{height}")
    if a is None:
        failures.append("no audio stream")
    duration = float(info.get("format", {}).get("duration", 0))
    expected = audio.total_duration_s
    if abs(duration - expected) > expected * DURATION_TOLERANCE:
        failures.append(f"duration {duration:.2f}s is not within {DURATION_TOLERANCE:.0%} of the audio's {expected:.2f}s")
    summary = (f"{v['width']}x{v['height']} " if v else "") + f"{duration:.2f}s against {expected:.2f}s of audio"
    return QAReport(episode_id=audio.episode_id, reviewer=REVIEWER, hard_gate_failures=failures, summary=summary)
