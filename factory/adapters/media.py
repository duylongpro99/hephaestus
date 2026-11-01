"""Build the provider serving each media purpose from config/media.yaml.

A profile names one provider per purpose (speech, image, video, publishing). Stations only see
the purpose's protocol; which vendor stands behind it is this file's and the config's business.
"""

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from factory.adapters.costs import MediaError, MediaPrice
from factory.adapters.image.base import ImageGenerator
from factory.adapters.publishing.base import VideoPublisher
from factory.adapters.speech.base import SpeechSynthesizer
from factory.adapters.video.base import VideoRenderer
from factory.config import CONFIG_DIR, REPO_ROOT, pack_module
from factory.tools.language_pack import LanguagePack

MEDIA_CONFIG_PATH = CONFIG_DIR / "media.yaml"
PROFILE_ENV = "FACTORY_MEDIA_PROFILE"
DEFAULT_PROFILE = "fake"

PURPOSES: dict[str, str] = {
    "fake_speech": "speech", "azure_speech": "speech",
    "fake_image": "image", "cloudflare_workers_ai": "image", "deepinfra": "image",
    "ffmpeg_pillow": "video",
    "export": "publishing", "youtube": "publishing",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfig(_Strict):
    type: Literal["fake_speech", "azure_speech", "fake_image", "cloudflare_workers_ai", "deepinfra",
                  "ffmpeg_pillow", "export", "youtube"]
    model: str | None = None
    env: dict[str, str] = {}  # what the provider reads from the environment -> the variable holding it
    options: dict[str, Any] = {}

    @property
    def purpose(self) -> str:
        return PURPOSES[self.type]


class PurposeConfig(_Strict):
    provider: str


class SpeechConfig(PurposeConfig):
    voices: dict[str, str]  # pack voice key -> the provider's voice id
    sample_rate: int = 24_000


class ProfileConfig(_Strict):
    speech: SpeechConfig
    image: PurposeConfig
    video: PurposeConfig
    publishing: PurposeConfig


class MediaConfig(_Strict):
    providers: dict[str, ProviderConfig]
    prices: dict[str, dict[str, MediaPrice]] = {}  # provider -> model -> price
    profiles: dict[str, ProfileConfig]

    @model_validator(mode="before")
    @classmethod
    def _prices(cls, data):
        data = dict(data)
        data["prices"] = {
            provider: {model: MediaPrice(**p) for model, p in (models or {}).items()}
            for provider, models in (data.get("prices") or {}).items()
        }
        return data

    @model_validator(mode="after")
    def _providers_fit_purposes(self):
        for name, profile in self.profiles.items():
            for purpose in ("speech", "image", "video", "publishing"):
                provider = getattr(profile, purpose).provider
                if provider not in self.providers:
                    raise ValueError(f"profile {name}: {purpose} uses undefined provider {provider!r}")
                if self.providers[provider].purpose != purpose:
                    raise ValueError(f"profile {name}: {purpose} provider {provider!r} is a "
                                     f"{self.providers[provider].purpose} provider")
        return self

    def profile(self, name: str) -> ProfileConfig:
        if name not in self.profiles:
            raise MediaError(f"no media profile {name!r} in {MEDIA_CONFIG_PATH.name}; "
                             f"profiles: {', '.join(self.profiles)}")
        return self.profiles[name]

    def price(self, provider: str, model: str) -> MediaPrice | None:
        return self.prices.get(provider, {}).get(model)


def load_media_config(path: Path = MEDIA_CONFIG_PATH) -> MediaConfig:
    return MediaConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def default_profile() -> str:
    return os.environ.get(PROFILE_ENV) or DEFAULT_PROFILE


def secret(name: str, provider: ProviderConfig, what: str) -> str:
    """The value of the environment variable `provider.env[what]`; a clear error when it is unset."""
    var = provider.env.get(what)
    if not var:
        raise MediaError(f"media provider {name} needs env.{what} in {MEDIA_CONFIG_PATH.name}")
    value = os.environ.get(var)
    if not value:
        raise MediaError(f"${var} is not set (the {what} for media provider {name})")
    return value


def speech_for(profile: str, pack: LanguagePack, config: MediaConfig | None = None) -> SpeechSynthesizer:
    """The synthesizer for `pack` in `profile`; every voice the pack offers must be mapped."""
    config = config or load_media_config()
    speech = config.profile(profile).speech
    missing = [v.key for v in pack.voices if v.key not in speech.voices]
    if missing:
        raise MediaError(f"media profile {profile} has no provider voice for {', '.join(missing)} "
                         f"(pack {pack.code}); add them under profiles.{profile}.speech.voices")
    name, provider = speech.provider, config.providers[speech.provider]
    voices = {v.key: speech.voices[v.key] for v in pack.voices}
    if provider.type == "fake_speech":
        from factory.adapters.speech.fake import FakeSpeech

        return FakeSpeech(pack, voices, speech.sample_rate)
    from factory.adapters.speech.azure_speech import AzureSpeech

    return AzureSpeech(
        key=secret(name, provider, "key"), region=secret(name, provider, "region"), voices=voices,
        sample_rate=speech.sample_rate, price=config.price(name, provider.model or ""),
        max_requests_per_minute=provider.options.get("max_requests_per_minute"), name=name,
    )


def image_for(profile: str, config: MediaConfig | None = None) -> ImageGenerator:
    """The image generator in `profile`."""
    config = config or load_media_config()
    name = config.profile(profile).image.provider
    provider = config.providers[name]
    if provider.type == "fake_image":
        from factory.adapters.image.fake import FakeImage

        return FakeImage()
    if not provider.model:
        raise MediaError(f"media provider {name} needs a model in {MEDIA_CONFIG_PATH.name}")
    common = dict(name=name, model=provider.model, price=config.price(name, provider.model),
                  style_suffix=provider.options.get("style_suffix", ""),
                  width=int(provider.options.get("width", 1024)), height=int(provider.options.get("height", 576)))
    if provider.type == "cloudflare_workers_ai":
        account_id, token = secret(name, provider, "account_id"), secret(name, provider, "token")
        from factory.adapters.image.cloudflare_workers_ai import CloudflareWorkersAI

        return CloudflareWorkersAI(account_id=account_id, token=token, **common)
    api_key = secret(name, provider, "key")
    from factory.adapters.image.deepinfra import DeepInfra

    return DeepInfra(api_key=api_key, **common)


def video_for(profile: str, pack: LanguagePack | None = None, config: MediaConfig | None = None) -> VideoRenderer:
    """The renderer in `profile`, with the pack's caption font when the pack ships one."""
    config = config or load_media_config()
    config.profile(profile)  # ffmpeg_pillow is the only renderer so far
    from factory.adapters.video.ffmpeg_pillow import FFmpegPillowRenderer

    return FFmpegPillowRenderer(font=pack_font(pack) if pack is not None else None)


def pack_font(pack: LanguagePack) -> Path | None:
    """The first of the pack's fonts that exists, as a path relative to the pack's directory."""
    pack_dir = Path(pack_module(pack.code).__file__).resolve().parent
    for font in pack.fonts:
        path = Path(font) if Path(font).is_absolute() else pack_dir / font
        if path.is_file():
            return path
    return None


def publisher_for(profile: str, artifact_root: Path, config: MediaConfig | None = None) -> VideoPublisher:
    """The publisher in `profile`; the export provider writes under the artifact store root."""
    config = config or load_media_config()
    name = config.profile(profile).publishing.provider
    provider = config.providers[name]
    if provider.type == "export":
        from factory.adapters.publishing.export import ExportPublisher

        return ExportPublisher(artifact_root / provider.options.get("dir", "_export"))
    from factory.adapters.publishing.youtube import YouTubePublisher

    return YouTubePublisher(token=repo_path(secret(name, provider, "token")),
                            category_id=str(provider.options.get("category_id", "27")))


def repo_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path
