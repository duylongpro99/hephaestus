"""Load KEY=VALUE pairs from the repo's gitignored .env file into the process environment."""

import os
from pathlib import Path

from factory.config import REPO_ROOT

ENV_PATH = REPO_ROOT / ".env"


def load_dotenv(path: Path = ENV_PATH) -> list[str]:
    """Set each variable not already in the environment; return the names that were set."""
    if not path.exists():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
