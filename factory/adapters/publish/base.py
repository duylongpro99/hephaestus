"""Publishing adapter interface (C10). Real platforms and the fake implement the same protocol."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from factory.contracts import PublishPackage


@dataclass(frozen=True)
class Upload:
    external_id: str
    quota_units: int


class Publisher(Protocol):
    platform: str

    def upload(self, video: Path, package: PublishPackage) -> Upload:
        """Upload `video` as private with the package's metadata; return the platform's video id."""
        ...

    def schedule(self, external_id: str, publish_at: datetime) -> None:
        """Set when the private video goes public. Idempotent per external_id."""
        ...
