"""Fake image generator: a solid-colour PNG whose colour comes from the prompt. No network."""

import hashlib
import struct
import zlib
from pathlib import Path

from factory.adapters.costs import Charge
from factory.adapters.image.base import ImageRequest


def colour(prompt: str) -> tuple[int, int, int]:
    """A mid-dark colour, so white burned-in text stays legible on it."""
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return tuple(40 + b % 120 for b in digest[:3])


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    row = b"\x00" + bytes(rgb) * width  # filter byte 0, then RGB pixels
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(row * height, 9)) + _chunk(b"IEND", b""))


class FakeImage:
    identity = "fake_image/solid-png-1"

    def generate(self, request: ImageRequest, out_path: Path) -> list[Charge]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(solid_png(request.width, request.height, colour(request.prompt)))
        return []
