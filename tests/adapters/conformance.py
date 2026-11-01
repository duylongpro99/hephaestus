"""What every provider of a media purpose must do, whatever vendor stands behind it.

Each check takes a ready provider, so the fake providers run it offline and the real ones run it
in the `live` smoke tests with the same assertions.
"""

import json
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from factory.adapters.image.base import ImageGenerator, ImageRequest
from factory.adapters.publishing.base import VideoPublisher
from factory.adapters.speech.base import SpeechRequest, SpeechResult, SpeechSynthesizer
from factory.adapters.video.base import VideoRenderer
from factory.contracts import PublishPackage, RenderProps


def check_speech(speech: SpeechSynthesizer, request: SpeechRequest, out_path: Path) -> SpeechResult:
    assert speech.identity
    result = speech.synthesize(request, out_path)
    with wave.open(str(out_path)) as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        seconds = wav.getnframes() / wav.getframerate()
    assert result.duration_s > 0 and abs(result.duration_s - seconds) < 0.01
    if result.words is not None:
        starts = [w.start_s for w in result.words]
        assert starts == sorted(starts)
        assert all(0 <= w.start_s <= w.end_s <= result.duration_s + 0.05 for w in result.words)
    assert all(c.usd >= 0 for c in result.charges)
    return result


def check_image(images: ImageGenerator, request: ImageRequest, out_path: Path) -> None:
    assert images.identity
    charges = images.generate(request, out_path)
    assert out_path.read_bytes().startswith(b"\x89PNG")
    with Image.open(out_path) as img:
        assert img.size == (request.width, request.height)
    assert all(c.usd >= 0 for c in charges)


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def check_video(renderer: VideoRenderer, props: RenderProps, resolve, media_dir: Path) -> Path:
    assert renderer.identity
    path = renderer.render(props, resolve, media_dir)
    info = probe(path)
    codecs = sorted((s["codec_type"], s["codec_name"]) for s in info["streams"])
    assert codecs == [("audio", "aac"), ("video", "h264")]
    assert abs(float(info["format"]["duration"]) - props.total_duration_s) < 0.25
    return path


def check_publisher(publisher: VideoPublisher, video: Path, package: PublishPackage) -> str:
    assert publisher.platform and publisher.identity
    upload = publisher.upload(video, package)
    assert upload.external_id and upload.quota_units >= 0
    when = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)
    for _ in range(2):  # scheduling twice is not an error
        assert publisher.schedule(upload.external_id, when, package) >= 0
    return upload.external_id
