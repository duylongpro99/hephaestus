"""Video rendering (C8): RenderProps plus their media -> one master MP4. Every renderer implements this."""

from pathlib import Path
from typing import Callable, Protocol

from factory.adapters.costs import MediaError
from factory.contracts import RenderProps


class VideoError(MediaError):
    pass


class VideoRenderer(Protocol):
    identity: str  # the renderer and the versions of its tools; part of the station_version

    def render(self, props: RenderProps, resolve: Callable[[str], Path], media_dir: Path) -> Path:
        """Write the master MP4 (H.264 video, AAC audio) under `media_dir` and return its path."""
        ...
