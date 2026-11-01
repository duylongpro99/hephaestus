"""DeepInfra: FLUX.2 [klein] over its OpenAI-compatible images endpoint, billed per megapixel."""

import base64
from pathlib import Path

import httpx

from factory.adapters.costs import Charge, MediaPrice, charge
from factory.adapters.image.base import ImageError, ImageRequest, fit_image

API = "https://api.deepinfra.com/v1/openai/images/generations"


class DeepInfra:
    def __init__(self, *, api_key: str, model: str, name: str = "deepinfra-images", price: MediaPrice | None = None,
                 style_suffix: str = "", width: int = 1024, height: int = 576, timeout_s: float = 120.0,
                 client: httpx.Client | None = None):
        self.model, self.name, self.price, self.style_suffix = model, name, price, style_suffix
        self.width, self.height = width, height
        self.client = client or httpx.Client(timeout=timeout_s)
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.identity = f"deepinfra/{model}@{width}x{height}#{style_suffix}"

    def generate(self, request: ImageRequest, out_path: Path) -> list[Charge]:
        # The OpenAI-compatible endpoint takes no seed, so the same prompt may draw a different picture;
        # the stored artifact is reused by station_version, so that only matters on a forced re-run.
        prompt = f"{request.prompt}, {self.style_suffix}" if self.style_suffix else request.prompt
        payload = {"model": self.model, "prompt": prompt, "size": f"{self.width}x{self.height}", "n": 1,
                   "response_format": "b64_json"}
        try:
            response = self.client.post(API, headers=self.headers, json=payload)
        except httpx.HTTPError as exc:
            raise ImageError(f"{self.name}: request failed ({exc})") from exc
        if response.status_code in (402, 429):
            raise ImageError(f"{self.name}: out of credit or rate limited (HTTP {response.status_code}: "
                             f"{response.text[:200]}); top up or switch the profile's image provider in "
                             f"config/media.yaml")
        if response.status_code >= 400:
            raise ImageError(f"{self.name}: HTTP {response.status_code}: {response.text[:200]}")
        try:
            image = response.json()["data"][0]["b64_json"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ImageError(f"{self.name}: no image in the response") from exc
        fit_image(base64.b64decode(image), request.width, request.height, out_path)
        return [charge(self.name, self.model, self.width * self.height, self.price)]
