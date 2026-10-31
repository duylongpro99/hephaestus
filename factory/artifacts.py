"""Content-addressed artifact store (architecture §4 and §4.5).

An artifact lives at artifacts/{channel}/{season or "adhoc"}/{episode}/{station}@{hash}.json;
media files it points to (audio, images, video) live in the sibling directory {station}@{hash}/.
The hash covers the station's inputs and its station_version, so a prompt, model or code
change never reuses an old output, and rolling the change back finds the old output again.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from pydantic import BaseModel

from factory.config import REPO_ROOT
from factory.contracts import CostEntry

M = TypeVar("M", bound=BaseModel)
ARTIFACT_ROOT = REPO_ROOT / "artifacts"
# Adapter code shapes every LLM station's request, so it is part of each station_version.
ADAPTER_SOURCES = tuple(sorted((REPO_ROOT / "factory" / "adapters" / "llm").glob("*.py")))


SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")


def safe_name(item_id: str) -> str:
    """An LLM-written id (a line or segment id) used as a file name; anything path-like is refused."""
    if not SAFE_NAME.fullmatch(item_id):
        raise ValueError(f"id {item_id!r} cannot name a file; ids use letters, digits, '_' and '-' only")
    return item_id


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


@dataclass
class Produced:
    envelope: dict
    path: Path
    reused: bool  # True when the store already held the output for these inputs

    @property
    def artifact(self) -> dict:
        return self.envelope["artifact"]


# Given the output's media directory, return the artifact and any extra envelope fields.
Builder = Callable[[Path], tuple[BaseModel, dict]]


class ArtifactStore:
    def __init__(self, root: Path = ARTIFACT_ROOT):
        self.root = root

    def path(self, channel: str, episode: str, station: str, digest: str, season: str | None = None) -> Path:
        return self.root / channel / (season or "adhoc") / episode / f"{station}@{digest}.json"

    def uri(self, path: Path) -> str:
        """A path relative to the store root, as contracts and Postgres pointers record it."""
        return path.relative_to(self.root).as_posix()

    def resolve(self, uri: str) -> Path:
        return self.root / uri

    def read(self, uri: str) -> dict:
        return json.loads(self.resolve(uri).read_text(encoding="utf-8"))

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
        # Write then rename, so a killed process never leaves a half-written envelope that reads as done.
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def read_envelope(
        self, *, channel: str, episode: str, station: str, version: str, inputs: list, season: str | None = None,
    ) -> dict | None:
        """Return the stored envelope for exactly these inputs and station_version, if any."""
        path = self.path(channel, episode, station, artifact_hash(inputs, version), season)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def produce(
        self, *, channel: str, episode: str, station: str, version: str, inputs: list, build: Builder,
        season: str | None = None, fresh: bool = False,
    ) -> Produced:
        """Return the stored output for these inputs, or build and store it.

        `build` receives the output's media directory (not yet created) for files the artifact
        points to; it runs only when the store has no output for exactly these inputs and version.
        """
        path = self.path(channel, episode, station, artifact_hash(inputs, version), season)
        if path.exists() and not fresh:
            return Produced(json.loads(path.read_text(encoding="utf-8")), path, reused=True)
        artifact, extra = build(path.with_suffix(""))
        self.write(channel=channel, episode=episode, station=station, version=version, inputs=inputs,
                   artifact=artifact, season=season, extra=extra)
        return Produced(json.loads(path.read_text(encoding="utf-8")), path, reused=False)


def load(model: type[M], data: dict) -> M:
    """Validate a stored artifact; computed fields such as `passed` are written out but not read back."""
    return model.model_validate({k: v for k, v in data.items() if k not in model.model_computed_fields})


@dataclass
class Built:
    """What a station's build step returns: its artifact, what it spent, and extra envelope fields."""

    artifact: BaseModel
    costs: list[CostEntry] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


class Producer:
    """Produces one episode's artifacts through the store.

    `ledger` holds the recorded cost of every output produced so far, including reused ones, for
    reports that show what an episode's artifacts cost in total.
    """

    def __init__(self, store: ArtifactStore, channel: str, episode: str, season: str | None = None,
                 fresh: bool = False):
        self.store, self.channel, self.episode, self.season, self.fresh = store, channel, episode, season, fresh
        self.produced: list[Produced] = []
        self.ledger: list[CostEntry] = []

    def produce(self, station: str, version: str, inputs: list, model: type[M], build: Callable[[Path], Built]) -> M:
        def store_build(media: Path) -> tuple[BaseModel, dict]:
            built = build(media)
            return built.artifact, {**built.extra, "cost": [c.model_dump(mode="json") for c in built.costs]}

        result = self.store.produce(channel=self.channel, episode=self.episode, station=station, version=version,
                                    inputs=inputs, build=store_build, season=self.season, fresh=self.fresh)
        self.produced.append(result)
        self.ledger += [CostEntry.model_validate(c) for c in result.envelope.get("cost", [])]
        return load(model, result.artifact)

    @property
    def last(self) -> Produced:
        return self.produced[-1]
