"""A7 Visual Director and C6 images (architecture §7).

A7 is a deterministic stand-in here: one shot per segment, its prompt built from the channel
persona, the episode title and the segment type. C6 draws each shot through the image generator.
"""

from pathlib import Path
from typing import Callable

from factory.adapters.costs import Charge, MediaError, ledger_entries
from factory.adapters.image.base import ImageGenerator, ImageRequest
from factory.artifacts import safe_name
from factory.config import ResolvedConfig
from factory.contracts import Script, Shot, ShotList

WIDTH, HEIGHT = 1920, 1080
STATION = "c6_images"  # the station its image costs are recorded under


def shoot(
    script: Script, config: ResolvedConfig, images: ImageGenerator, media_dir: Path, uri_of: Callable[[Path], str],
) -> tuple[ShotList, list[Charge]]:
    """The shot list, and what the image generator charged for it."""
    shots, charges = [], []
    for segment in script.segments:
        prompt = (f"{config.channel.persona.name}'s channel, episode '{script.title_working}', "
                  f"{segment.type} segment {segment.id}")
        path = media_dir / f"{safe_name(segment.id)}.png"
        try:
            charges.extend(images.generate(ImageRequest.for_prompt(prompt, WIDTH, HEIGHT), path))
        except MediaError as exc:
            exc.costs = ledger_entries(STATION, charges)
            raise
        shots.append(Shot(segment_id=segment.id, template=segment.layout or segment.type, assets=[uri_of(path)],
                          image_prompts=[prompt]))
    return ShotList(episode_id=script.episode_id, shots=shots), charges
