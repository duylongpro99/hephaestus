"""Publishing (C10): upload a rendered episode privately, then schedule it. Every platform implements this."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from factory.adapters.costs import MediaError
from factory.contracts import PublishPackage


class PublishError(MediaError):
    """A publishing failure. `video_may_exist` is False only when the platform cannot have received any of
    the video (a refused token, an exhausted quota, a lookup that failed before the upload began), so a
    retry may upload without first looking for a copy."""

    def __init__(self, message: str, *, video_may_exist: bool = True):
        super().__init__(message)
        self.video_may_exist = video_may_exist


@dataclass(frozen=True)
class Upload:
    external_id: str
    quota_units: int


def episode_tag(episode_id: str) -> str:
    """A tag on every upload that finds it again after a crash lost the receipt."""
    return f"ep-{episode_id}"


def upload_tags(package: PublishPackage, language: str) -> list[str]:
    """The tags an upload in `language` carries: the package's, then the episode tag."""
    return [*package.tags.get(language, []), episode_tag(package.episode_id)]


class VideoPublisher(Protocol):
    platform: str  # where episodes go, recorded on the PublishReceipt, e.g. "youtube" or "export"
    identity: str

    def find(self, episode_id: str) -> tuple[str | None, int]:
        """The id of this episode's video on the platform, if it is there, and the quota units spent looking."""
        ...

    def video_tags(self, external_id: str) -> list[str] | None:
        """The tags of a video that belongs to this account, or None when the account has no such video."""
        ...

    def upload(self, video: Path, package: PublishPackage) -> Upload:
        """Upload `video` as private with the package's metadata; return the platform's video id.

        Must not create a second copy when the same episode was already uploaded (a retry after a
        crash that lost the receipt)."""
        ...

    def schedule(self, external_id: str, publish_at: datetime, package: PublishPackage) -> int:
        """Set when the private video goes public, keeping the package's audience and disclosure labels;
        return the quota units spent. Idempotent."""
        ...
