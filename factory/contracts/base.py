from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Base for every artifact contract.

    Each subclass declares `schema_version: str = "<semver>"`. Bump it whenever the
    generated JSON Schema changes; `tests/test_contracts.py` fails if a committed
    schema drifts without a bump.
    """

    model_config = ConfigDict(extra="forbid")


class Part(BaseModel):
    """Base for nested models inside a contract."""

    model_config = ConfigDict(extra="forbid")
