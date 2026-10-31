from factory.contracts.base import Contract, Part


class Shot(Part):
    segment_id: str
    template: str
    assets: list[str]  # image uris relative to the artifact store root
    image_prompts: list[str]
    pose: str | None = None
    expression: str | None = None
    on_screen_text: list[str] = []


class ShotList(Contract):
    """What each segment shows (architecture §4.4), written by A7."""

    schema_version: str = "1.0.0"
    episode_id: str
    shots: list[Shot]
