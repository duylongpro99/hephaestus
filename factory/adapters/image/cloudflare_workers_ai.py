"""Cloudflare Workers AI: FLUX.2 [klein] over the REST API, billed in neurons with a daily free allocation."""

import base64
from pathlib import Path

import httpx

from factory.adapters.costs import Charge, MediaPrice, charge
from factory.adapters.image.base import ImageError, ImageRequest, fit_image

API = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
QUOTA_CODES = {4006}  # "you have used up your daily free allocation of neurons"


class CloudflareWorkersAI:
    def __init__(self, *, account_id: str, token: str, model: str, name: str = "cloudflare-images",
                 price: MediaPrice | None = None, style_suffix: str = "", width: int = 1024, height: int = 576,
                 timeout_s: float = 120.0, client: httpx.Client | None = None):
        self.url = API.format(account_id=account_id, model=model)
        self.model, self.name, self.price, self.style_suffix = model, name, price, style_suffix
        self.width, self.height = width, height
        self.client = client or httpx.Client(timeout=timeout_s)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.identity = f"cloudflare_workers_ai/{model}@{width}x{height}#{style_suffix}"

    def generate(self, request: ImageRequest, out_path: Path) -> list[Charge]:
        prompt = f"{request.prompt}, {self.style_suffix}" if self.style_suffix else request.prompt
        fields = {"prompt": prompt, "width": self.width, "height": self.height, "seed": request.seed}
        try:
            response = self.client.post(self.url, headers=self.headers,
                                        files={k: (None, str(v)) for k, v in fields.items()})
        except httpx.HTTPError as exc:
            raise ImageError(f"{self.name}: request failed ({exc})") from exc
        body = json_body(response)
        if any(e.get("code") in QUOTA_CODES for e in body.get("errors") or []):
            raise ImageError(f"{self.name}: daily quota exhausted ({errors(body)}); switch the "
                             f"profile's image provider (e.g. to deepinfra-images) in config/media.yaml")
        if response.status_code == 429:
            raise ImageError(f"{self.name}: rate limited ({errors(body) or 'HTTP 429'}); try again shortly")
        if response.status_code >= 400 or body.get("success") is False:
            raise ImageError(f"{self.name}: HTTP {response.status_code}: {errors(body) or response.text[:200]}")
        image = (body.get("result") or {}).get("image") or body.get("image")
        if not image:
            raise ImageError(f"{self.name}: no image in the response")
        fit_image(base64.b64decode(image), request.width, request.height, out_path)
        return [charge(self.name, self.model, 1, self.price)]



def json_body(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def errors(body: dict) -> str:
    return "; ".join(f"{e.get('code')}: {e.get('message')}" for e in body.get("errors") or [])
