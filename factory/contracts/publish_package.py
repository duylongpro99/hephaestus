from datetime import datetime

from factory.contracts.base import Contract, Part


class Chapter(Part):
    start_s: float
    title: str


class PublishPackage(Contract):
    """Everything the publisher sends with the video (architecture §4.4), written by A9 and A11."""

    schema_version: str = "1.0.0"
    episode_id: str
    video_uri: str
    title: dict[str, str]  # keyed by language
    description: dict[str, str]
    tags: dict[str, list[str]]
    chapters: list[Chapter]
    thumbnail_text: str | None = None
    made_for_kids: bool
    contains_synthetic_media: bool
    playlist_ids: list[str] = []
    publish_at: datetime | None = None
