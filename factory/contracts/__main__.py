"""Export every contract's JSON Schema: `uv run python -m factory.contracts`."""

import json
from pathlib import Path

from factory.contracts import CONTRACTS

SCHEMA_DIR = Path(__file__).parent / "schemas"


def render(model) -> str:
    return json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True) + "\n"


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for name, model in CONTRACTS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        path.write_text(render(model))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
