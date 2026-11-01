"""Publishing (C10): upload a rendered episode privately, then schedule it. Every platform implements this."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from factory.adapters.costs import MediaError
from factory.contracts import PublishPackage


class PublishError(MediaError):
    pass


@dataclass(frozen=True)
class Upload:
    external_id: str
    quota_units: int


class VideoPublisher(Protocol):
    platform: str  # where episodes go, recorded on the PublishReceipt, e.g. "youtube" or "export"
    identity: str

    def upload(self, video: Path, package: PublishPackage) -> Upload:
        """Upload `video` as private with the package's metadata; return the platform's video id.

        Must not create a second copy when the same episode was already uploaded (a retry after a
        crash that lost the receipt)."""
        ...

    def schedule(self, external_id: str, publish_at: datetime, package: PublishPackage) -> int:
        """Set when the private video goes public, keeping the package's audience and disclosure labels;
        return the quota units spent. Idempotent."""
        ...
