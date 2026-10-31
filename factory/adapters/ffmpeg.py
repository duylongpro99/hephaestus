"""Run FFmpeg and ffprobe. Every encode is bit-exact, so the same inputs give the same bytes."""

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require(*tools: str) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise FFmpegError(f"{', '.join(missing)} not found on PATH; install FFmpeg")


def run(*args: str | Path) -> None:
    require("ffmpeg")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise FFmpegError(f"ffmpeg failed ({done.returncode}): {done.stderr.strip()[-2000:]}")


def probe(path: Path) -> dict:
    require("ffprobe")
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}: {done.stderr.strip()}")
    return json.loads(done.stdout)


def version() -> str:
    """The first line of `ffmpeg -version`; encoder changes alter output bytes, so renders key on it."""
    require("ffmpeg")
    done = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    return done.stdout.splitlines()[0] if done.stdout else "ffmpeg unknown"
