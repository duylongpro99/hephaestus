"""Fake image generator: a solid-colour PNG whose colour comes from the prompt. No network."""

import hashlib
import struct
import zlib
from pathlib import Path


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


class FakeImageProvider:
    vendor = "fake"
    identity = "fake/solid-png-1"

    def generate(self, prompt: str, width: int, height: int, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(solid_png(width, height, colour(prompt)))
