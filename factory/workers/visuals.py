"""A7 Visual Director and C6 images (architecture §7).

A7 is a deterministic stand-in here: one shot per segment, its prompt built from the channel
persona, the episode title and the segment type. C6 draws each shot through the image adapter.
"""

from pathlib import Path
from typing import Callable

from factory.adapters.image.base import ImageProvider
from factory.artifacts import safe_name
from factory.config import ResolvedConfig
from factory.contracts import Script, Shot, ShotList

WIDTH, HEIGHT = 1920, 1080


def shoot(
    script: Script, config: ResolvedConfig, images: ImageProvider, media_dir: Path, uri_of: Callable[[Path], str],
) -> ShotList:
    shots = []
    for segment in script.segments:
        prompt = (f"{config.channel.persona.name}'s channel, episode '{script.title_working}', "
                  f"{segment.type} segment {segment.id}")
        path = media_dir / f"{safe_name(segment.id)}.png"
        images.generate(prompt, WIDTH, HEIGHT, path)
        shots.append(Shot(segment_id=segment.id, template=segment.layout or segment.type, assets=[uri_of(path)],
                          image_prompts=[prompt]))
    return ShotList(episode_id=script.episode_id, shots=shots)
