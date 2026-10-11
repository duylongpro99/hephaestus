"""Content-addressed artifact store (architecture §4 and §4.5).

An artifact lives at artifacts/{channel}/{season or "adhoc"}/{episode}/{station}@{hash}.json.
The hash covers the station's inputs and its station_version, so a prompt, model or code
change never reuses an old output, and rolling the change back finds the old output again.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from factory.config import REPO_ROOT

ARTIFACT_ROOT = REPO_ROOT / "artifacts"
# Adapter code shapes every LLM station's request, so it is part of each station_version.
ADAPTER_SOURCES = tuple(sorted((REPO_ROOT / "factory" / "adapters" / "llm").glob("*.py")))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def station_version(model_id: str, *sources: Path) -> str:
    """Prompt hash + model id + code version: a hash over the station's files and its model."""
    digest = hashlib.sha256(model_id.encode("utf-8"))
    for path in sorted(sources):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return f"{model_id}+{digest.hexdigest()[:12]}"


def artifact_hash(inputs: list, version: str) -> str:
    payload = canonical({"inputs": [canonical(i) for i in inputs], "station_version": version})
    return sha256_text(payload)[:16]


class ArtifactStore:
    def __init__(self, root: Path = ARTIFACT_ROOT):
        self.root = root

    def path(self, channel: str, episode: str, station: str, digest: str, season: str | None = None) -> Path:
        return self.root / channel / (season or "adhoc") / episode / f"{station}@{digest}.json"

    def write(
        self, *, channel: str, episode: str, station: str, version: str, inputs: list, artifact: BaseModel,
        season: str | None = None, extra: dict | None = None,
    ) -> Path:
        digest = artifact_hash(inputs, version)
        path = self.path(channel, episode, station, digest, season)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "station": station,
            "station_version": version,
            "hash": digest,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifact_type": type(artifact).__name__,
            "artifact": artifact.model_dump(mode="json"),
            **(extra or {}),
        }
        path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def read_envelope(
        self, *, channel: str, episode: str, station: str, version: str, inputs: list, season: str | None = None,
    ) -> dict | None:
        """Return the stored envelope for exactly these inputs and station_version, if any."""
        path = self.path(channel, episode, station, artifact_hash(inputs, version), season)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
