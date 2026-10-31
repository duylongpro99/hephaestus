"""Image generation adapter interface (C6). Real vendors and the fake implement the same protocol."""

from pathlib import Path
from typing import Protocol


class ImageProvider(Protocol):
    vendor: str
    identity: str

    def generate(self, prompt: str, width: int, height: int, out_path: Path) -> None:
        """Write a PNG for `prompt` at `width` x `height` pixels."""
        ...
