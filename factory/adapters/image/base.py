"""Image generation (C6): draw one shot from a prompt. Every provider implements this protocol."""

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps

from factory.adapters.costs import Charge, MediaError


class ImageError(MediaError):
    pass


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    width: int
    height: int
    seed: int  # derived from the prompt, so the same input makes the same request

    @classmethod
    def for_prompt(cls, prompt: str, width: int, height: int) -> "ImageRequest":
        seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
        return cls(prompt=prompt, width=width, height=height, seed=seed)


class ImageGenerator(Protocol):
    identity: str  # everything that changes the picture; part of the station_version

    def generate(self, request: ImageRequest, out_path: Path) -> list[Charge]:
        """Write a PNG of exactly `request.width` x `request.height` pixels to `out_path`."""
        ...


def fit_image(data: bytes, width: int, height: int, out_path: Path) -> None:
    """Save `data` (any format Pillow reads) as an RGB PNG of `width` x `height`: centre-crop to the
    aspect ratio, then scale, so a provider that draws a different size still fills the frame."""
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            fitted = ImageOps.fit(image.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
    except OSError as exc:
        raise ImageError(f"the provider returned something that is not an image ({exc})") from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fitted.save(out_path, format="PNG")
