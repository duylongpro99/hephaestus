"""C8 render: RenderProps -> master.mp4 (architecture §7).

A placeholder until Remotion arrives in build step 3: each caption becomes one frame (the
scene's image with the line's text drawn on it, via Pillow so any FFmpeg build works), shown
for the line's time on the audio track, then FFmpeg encodes the frames with the master audio.
"""

from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from factory.adapters import ffmpeg
from factory.artifacts import safe_name
from factory.contracts import RenderProps

FONT_SIZE = 64


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return [*lines, current] if current else lines


def caption_frame(image: Path, text: str, out_path: Path) -> None:
    """The scene image with `text` centred near the bottom, white with a dark outline."""
    with Image.open(image) as base:
        frame = base.convert("RGB")
    draw = ImageDraw.Draw(frame)
    font = ImageFont.load_default(size=FONT_SIZE)
    rows = wrap(draw, text, font, frame.width * 0.85)
    line_height = FONT_SIZE * 1.25
    y = frame.height - 120 - line_height * len(rows)
    for row in rows:
        x = (frame.width - draw.textlength(row, font=font)) / 2
        draw.text((x, y), row, font=font, fill="white", stroke_width=4, stroke_fill="black")
        y += line_height
    frame.save(out_path, format="PNG")


def render(props: RenderProps, resolve: Callable[[str], Path], media_dir: Path) -> Path:
    frames_dir = media_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for scene in props.scenes:
        for caption in scene.captions:
            frame = frames_dir / f"{safe_name(caption.line_id)}.png"
            caption_frame(resolve(scene.image_uri), caption.text, frame)
            entries.append((frame, caption.duration_s))
    if not entries:
        raise ValueError(f"{props.episode_id}: nothing to render; the props have no captions")
    playlist = media_dir / "frames.txt"
    lines = [f"file '{frame.relative_to(media_dir).as_posix()}'\nduration {seconds:.4f}" for frame, seconds in entries]
    lines.append(f"file '{entries[-1][0].relative_to(media_dir).as_posix()}'")  # the concat demuxer drops the last duration otherwise
    playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = media_dir / "master.mp4"
    ffmpeg.run(
        "-f", "concat", "-safe", "0", "-i", playlist, "-i", resolve(props.audio_uri),
        "-map", "0:v", "-map", "1:a",
        "-vf", f"fps={props.fps},scale={props.width}:{props.height},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        out,
    )
    return out
