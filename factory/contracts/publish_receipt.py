from datetime import datetime
from typing import Literal

from factory.contracts.base import Contract


class PublishReceipt(Contract):
    """Proof of an upload (architecture §4.4), stored by C10 before anything else touches the video."""

    schema_version: str = "1.0.0"
    episode_id: str
    platform: str
    external_id: str
    upload_ts: datetime
    publish_at: datetime | None = None
    status: Literal["private", "scheduled"]
    quota_units: int = 0
