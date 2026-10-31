from factory.contracts.base import Contract


class RenderedVideo(Contract):
    """The encoded episode video, written by C8 and checked by C9."""

    schema_version: str = "1.0.0"
    episode_id: str
    uri: str  # relative to the artifact store root
    sha256: str
    size_bytes: int
    width: int
    height: int
    fps: int
