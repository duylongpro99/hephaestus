"""Build the LLM provider for a factory role from config/llm.yaml."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from factory.adapters.llm.base import LLMError, LLMProvider, Price
from factory.config import CONFIG_DIR

LLM_CONFIG_PATH = CONFIG_DIR / "llm.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfig(_Strict):
    type: Literal["openai_compatible", "anthropic"]
    api_key_env: str
    base_url: str | None = None
    base_url_env: str | None = None  # read the URL from this variable instead (a private gateway, say)

    @model_validator(mode="after")
    def _one_url_source(self):
        if self.base_url and self.base_url_env:
            raise ValueError("set base_url or base_url_env, not both")
        if self.type == "openai_compatible" and not (self.base_url or self.base_url_env):
            raise ValueError("an openai_compatible provider needs base_url or base_url_env")
        return self

    def resolve_url(self) -> str | None:
        if not self.base_url_env:
            return self.base_url
        url = os.environ.get(self.base_url_env)
        if not url:
            raise LLMError(f"${self.base_url_env} is not set (the endpoint URL for this provider)")
        return url

    def resolve_key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise LLMError(f"${self.api_key_env} is not set (the API key for this provider)")
        return key


class RoleConfig(_Strict):
    provider: str
    model: str
    max_tokens: int
    params: dict[str, Any] = {}

    def identity(self) -> str:
        """provider/model plus a short hash of the request parameters, for station_version."""
        params = json.dumps(self.params, sort_keys=True, separators=(",", ":"))
        return f"{self.provider}/{self.model}#{hashlib.sha256(params.encode()).hexdigest()[:8]}"


class LLMConfig(_Strict):
    providers: dict[str, ProviderConfig]
    prices: dict[str, dict[str, Price]] = {}
    roles: dict[str, RoleConfig]

    @model_validator(mode="before")
    @classmethod
    def _prices(cls, data):
        data = dict(data)
        data["prices"] = {
            provider: {model: Price(**p) for model, p in (models or {}).items()}
            for provider, models in (data.get("prices") or {}).items()
        }
        return data

    @model_validator(mode="after")
    def _known_providers(self):
        unknown = {r.provider for r in self.roles.values()} - set(self.providers)
        if unknown:
            raise ValueError(f"roles use undefined providers: {sorted(unknown)}")
        return self

    def role(self, name: str) -> RoleConfig:
        if name not in self.roles:
            raise LLMError(f"no LLM role {name!r} in {LLM_CONFIG_PATH.name}; add it under roles:")
        return self.roles[name]


def load_llm_config(path: Path = LLM_CONFIG_PATH) -> LLMConfig:
    return LLMConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def provider_for(role: str, config: LLMConfig | None = None, client: Any = None) -> LLMProvider:
    """The provider serving `role`. Pass `client` to inject a fake SDK client in tests."""
    config = config or load_llm_config()
    role_cfg = config.role(role)
    provider_cfg = config.providers[role_cfg.provider]
    prices = config.prices.get(role_cfg.provider, {})
    if client is None:
        try:
            client = make_client(provider_cfg)
        except LLMError as exc:
            raise LLMError(f"role {role} uses provider {role_cfg.provider}, but {exc}") from exc
    common = dict(name=role_cfg.provider, model=role_cfg.model, client=client, params=role_cfg.params,
                  max_tokens=role_cfg.max_tokens, identity=role_cfg.identity())
    if provider_cfg.type == "anthropic":
        from factory.adapters.llm.anthropic_client import AnthropicProvider

        return AnthropicProvider(prices=prices, **common)
    from factory.adapters.llm.openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(price=prices.get(role_cfg.model), **common)


def role_identity(role: str, config: LLMConfig | None = None) -> str:
    return (config or load_llm_config()).role(role).identity()


def make_client(provider: ProviderConfig) -> Any:
    api_key, base_url = provider.resolve_key(), provider.resolve_url()
    if provider.type == "anthropic":
        import anthropic

        return anthropic.Anthropic(api_key=api_key, base_url=base_url)
    import openai

    return openai.OpenAI(api_key=api_key, base_url=base_url, timeout=600, max_retries=2)


def list_models(provider_name: str, config: LLMConfig | None = None) -> list[str]:
    """Model ids the provider's endpoint offers (GET /models)."""
    config = config or load_llm_config()
    if provider_name not in config.providers:
        raise LLMError(f"no provider {provider_name!r} in {LLM_CONFIG_PATH.name}")
    client = make_client(config.providers[provider_name])
    try:
        return sorted(model.id for model in client.models.list())
    except Exception as exc:  # the SDKs raise different error types; report any of them plainly
        raise LLMError(f"{provider_name}: could not list models: {exc}") from exc
