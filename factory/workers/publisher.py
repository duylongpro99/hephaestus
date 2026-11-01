"""C10 Publisher: upload once, then schedule (architecture §5).

An upload leaves a marker (a publish attempt) before the first byte goes out and swaps it for the
PublishReceipt when the platform answers. An existing receipt means the video is up. A marker without
a receipt means a run died mid-upload: the video may exist without its id, so the retry looks for it
and, when it cannot find it, stops for an operator rather than risk a second copy. Scheduling is
idempotent per external id.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from factory.adapters.publishing.base import PublishError, VideoPublisher
from factory.contracts import PublishPackage, PublishReceipt

MARKER_POLLS = 3  # lookups for a video an interrupted upload may have left, before asking an operator
MARKER_POLL_INTERVAL_S = 60.0  # a new upload can take a while to show in the channel's uploads list


class UploadUnconfirmed(Exception):
    """An earlier upload of the episode may have reached the platform, and it cannot be found."""


class Clock(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class UploadRecords(Protocol):
    """Where one episode's upload state for one platform lives (the orchestrator's database)."""

    def receipt(self) -> PublishReceipt | None: ...

    def attempt(self) -> datetime | None:
        """When an upload started that has no receipt yet."""
        ...

    def start(self, at: datetime) -> None:
        """Record, durably and at once, that an upload is starting."""
        ...

    def clear(self) -> None:
        """Forget the started upload: the platform received none of it."""
        ...

    def finish(self, receipt: PublishReceipt) -> None:
        """Store the receipt and forget the started upload, together."""
        ...


def resolve_command(episode_id: str, platform: str) -> str:
    return (f"factory publish resolve {episode_id} --platform {platform} "
            "--external-id <id> | --not-uploaded")


def upload(
    records: UploadRecords, publisher: VideoPublisher, video: Path, package: PublishPackage, clock: Clock,
) -> PublishReceipt:
    """The receipt for this episode on the publisher's platform, uploading only when no upload may exist."""
    existing = records.receipt()
    if existing is not None:
        return existing

    def receipt(external_id: str, units: int) -> PublishReceipt:
        return PublishReceipt(episode_id=package.episode_id, platform=publisher.platform, external_id=external_id,
                              upload_ts=clock.now(), status="private", quota_units=units)

    started = records.attempt()
    if started is not None:
        units = 0
        for poll in range(MARKER_POLLS):
            if poll:
                clock.sleep(MARKER_POLL_INTERVAL_S)
            found, spent = publisher.find(package.episode_id)
            units += spent
            if found:
                done = receipt(found, units)
                records.finish(done)
                return done
        raise UploadUnconfirmed(
            f"an upload of {package.episode_id} to {publisher.platform} started at {started.isoformat()} and "
            f"never stored its receipt, and no such video turned up after {MARKER_POLLS} lookups; check the "
            f"platform, then run `{resolve_command(package.episode_id, publisher.platform)}`")
    records.start(clock.now())
    try:
        done = publisher.upload(video, package)
    except PublishError as exc:
        if not exc.video_may_exist:
            records.clear()
        raise
    finished = receipt(done.external_id, done.quota_units)
    records.finish(finished)
    return finished


def publish_time(package: PublishPackage, now: datetime) -> datetime:
    """The package's slot, or, for an ad hoc episode without one, the next full hour a day from now."""
    if package.publish_at is not None:
        return package.publish_at
    return (now + timedelta(days=1, hours=1)).replace(minute=0, second=0, microsecond=0)


def schedule(
    receipt: PublishReceipt, publisher: VideoPublisher, publish_at: datetime, package: PublishPackage,
) -> PublishReceipt:
    """Schedule the video at `publish_at`. A receipt already scheduled at that time is returned as it is: the
    receipt only says scheduled after the platform accepted it, so a rerun spends no quota."""
    if receipt.status == "scheduled" and receipt.publish_at == publish_at:
        return receipt
    units = publisher.schedule(receipt.external_id, publish_at, package)
    return receipt.model_copy(update={"publish_at": publish_at, "status": "scheduled",
                                      "quota_units": receipt.quota_units + units})
