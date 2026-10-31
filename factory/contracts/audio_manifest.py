from pydantic import Field

from factory.contracts.base import Contract, Part


class WordTiming(Part):
    text: str
    start_s: float
    end_s: float


class LineAudio(Part):
    line_id: str
    uri: str  # relative to the artifact store root
    start_s: float  # where the line starts in the master track
    duration_s: float = Field(gt=0)
    pause_after_s: float = Field(ge=0)
    words: list[WordTiming] = []


class AudioManifest(Contract):
    """Every voiced line and the assembled master track (architecture §4.4), written by C4 and C5."""

    schema_version: str = "1.0.0"
    episode_id: str
    lines: list[LineAudio]
    master_uri: str
    sample_rate: int
    total_duration_s: float
    lufs: float | None = None  # integrated loudness after mastering; None until C5 measures it
