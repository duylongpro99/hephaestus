from factory.contracts.base import Contract, Part


class Caption(Part):
    line_id: str
    text: str
    start_s: float
    duration_s: float


class Scene(Part):
    segment_id: str
    template: str
    image_uri: str
    start_s: float
    duration_s: float
    captions: list[Caption]


class RenderProps(Contract):
    """Renderer input (architecture §4.4): a pure function of Script, AudioManifest and ShotList, by C7."""

    schema_version: str = "1.0.0"
    episode_id: str
    width: int
    height: int
    fps: int
    audio_uri: str
    total_duration_s: float
    scenes: list[Scene]
