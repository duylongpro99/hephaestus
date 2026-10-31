"""C10 Publisher: upload once, then schedule (architecture §5).

The upload stores its PublishReceipt before anything else touches the video, and an existing
receipt means the video is already up, so a crash between upload and scheduling never uploads
twice. Scheduling is idempotent per external id.
"""

from datetime import datetime, timedelta
from pathlib import Path

from factory.adapters.publish.base import Publisher
from factory.contracts import PublishPackage, PublishReceipt


def upload(
    existing: PublishReceipt | None, publisher: Publisher, video: Path, package: PublishPackage, now: datetime,
) -> tuple[PublishReceipt, bool]:
    """The receipt for this episode on the publisher's platform, and whether this call uploaded."""
    if existing is not None:
        return existing, False
    done = publisher.upload(video, package)
    receipt = PublishReceipt(episode_id=package.episode_id, platform=publisher.platform,
                             external_id=done.external_id, upload_ts=now, status="private",
                             quota_units=done.quota_units)
    return receipt, True


def publish_time(package: PublishPackage, now: datetime) -> datetime:
    """The package's slot, or, for an ad hoc episode without one, the next full hour a day from now."""
    if package.publish_at is not None:
        return package.publish_at
    return (now + timedelta(days=1, hours=1)).replace(minute=0, second=0, microsecond=0)


def schedule(receipt: PublishReceipt, publisher: Publisher, publish_at: datetime) -> PublishReceipt:
    publisher.schedule(receipt.external_id, publish_at)
    return receipt.model_copy(update={"publish_at": publish_at, "status": "scheduled"})
