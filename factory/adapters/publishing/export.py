"""Export publisher: "uploads" by copying the video and its metadata into a local directory, ready for a
manual upload. No network."""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from factory.adapters.publishing.base import PublishError, Upload
from factory.contracts import PublishPackage


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class ExportPublisher:
    platform = "export"
    identity = "export/1"

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def _meta_path(self, external_id: str) -> Path:
        return self.out_dir / f"{external_id}.json"

    def upload(self, video: Path, package: PublishPackage) -> Upload:
        external_id = "export-" + file_sha256(video)[:11]
        if self._meta_path(external_id).exists():  # already exported; keep its schedule
            return Upload(external_id=external_id, quota_units=0)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(video, self.out_dir / f"{external_id}.mp4")
        meta = {"privacy": "private", "publish_at": None, "package": package.model_dump(mode="json")}
        self._meta_path(external_id).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return Upload(external_id=external_id, quota_units=0)

    def schedule(self, external_id: str, publish_at: datetime, package: PublishPackage) -> int:
        path = self._meta_path(external_id)
        if not path.exists():
            raise PublishError(f"no exported video {external_id} in {self.out_dir}")
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["publish_at"] = publish_at.isoformat()
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0
