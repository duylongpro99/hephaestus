"""Cloudflare Workers AI and DeepInfra against a mock transport; `live` tests call them when secrets are set."""

import base64
import io
import json
import os

import httpx
import pytest
from PIL import Image

from factory.adapters import media
from factory.adapters.costs import MediaPrice
from factory.adapters.image.base import ImageError, ImageRequest
from factory.adapters.image.cloudflare_workers_ai import CloudflareWorkersAI
from factory.adapters.image.deepinfra import DeepInfra
from tests.adapters.conformance import check_image

REQUEST = ImageRequest.for_prompt("a quiet train station at dawn", 1920, 1080)


def jpeg_b64(width: int = 1024, height: int = 576) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (90, 120, 160)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def mock(handler) -> tuple[httpx.Client, list[httpx.Request]]:
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(record)), seen


def cloudflare(handler, **kwargs):
    client, seen = mock(handler)
    return CloudflareWorkersAI(account_id="acct", token="tok", model="@cf/black-forest-labs/flux-2-klein-4b",
                               client=client, **kwargs), seen


def deepinfra(handler, **kwargs):
    client, seen = mock(handler)
    return DeepInfra(api_key="key", model="black-forest-labs/FLUX-2-klein-4b", client=client, **kwargs), seen


def test_cloudflare_sends_a_multipart_request_and_fits_the_image(tmp_path):
    images, seen = cloudflare(lambda r: httpx.Response(200, json={"success": True, "result": {"image": jpeg_b64()}}),
                              style_suffix="flat illustration", price=MediaPrice(usd=0.00088))
    check_image(images, REQUEST, tmp_path / "shot.png")
    request = seen[0]
    assert str(request.url) == ("https://api.cloudflare.com/client/v4/accounts/acct/ai/run/"
                                "@cf/black-forest-labs/flux-2-klein-4b")
    assert request.headers["authorization"] == "Bearer tok"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content.decode()
    for value in ("a quiet train station at dawn, flat illustration", "1024", "576", str(REQUEST.seed)):
        assert value in body


def test_cloudflare_charges_one_image_at_the_configured_price(tmp_path):
    images, _ = cloudflare(lambda r: httpx.Response(200, json={"result": {"image": jpeg_b64()}}),
                           price=MediaPrice(usd=0.00088))
    [charge] = images.generate(REQUEST, tmp_path / "shot.png")
    assert (charge.vendor, charge.model, charge.usd) == ("cloudflare-images", "@cf/black-forest-labs/flux-2-klein-4b",
                                                         0.00088)


def test_cloudflare_quota_points_to_the_config_and_does_not_fall_back(tmp_path):
    quota = {"success": False, "errors": [{"code": 4006, "message": "daily free allocation of 10,000 neurons used"}]}
    images, seen = cloudflare(lambda r: httpx.Response(400, json=quota))
    with pytest.raises(ImageError, match="quota exhausted .*4006.*config/media.yaml"):
        images.generate(REQUEST, tmp_path / "shot.png")
    assert len(seen) == 1 and not (tmp_path / "shot.png").exists()


def test_a_cloudflare_rate_limit_is_not_reported_as_an_exhausted_quota(tmp_path):
    images, _ = cloudflare(lambda r: httpx.Response(429, json={"success": False, "errors": []}))
    with pytest.raises(ImageError, match="rate limited") as failed:
        images.generate(REQUEST, tmp_path / "shot.png")
    assert "quota" not in str(failed.value)


def test_cloudflare_errors_and_empty_responses_are_image_errors(tmp_path):
    images, _ = cloudflare(lambda r: httpx.Response(401, json={"success": False,
                                                               "errors": [{"code": 10000, "message": "bad token"}]}))
    with pytest.raises(ImageError, match="HTTP 401: 10000: bad token"):
        images.generate(REQUEST, tmp_path / "shot.png")
    images, _ = cloudflare(lambda r: httpx.Response(200, json={"success": True, "result": {}}))
    with pytest.raises(ImageError, match="no image"):
        images.generate(REQUEST, tmp_path / "shot.png")
    images, _ = cloudflare(lambda r: httpx.Response(200, json={"result": {"image": base64.b64encode(b"nope").decode()}}))
    with pytest.raises(ImageError, match="not an image"):
        images.generate(REQUEST, tmp_path / "shot.png")


def test_deepinfra_posts_openai_style_json_and_charges_per_pixel(tmp_path):
    images, seen = deepinfra(lambda r: httpx.Response(200, json={"data": [{"b64_json": jpeg_b64()}]}),
                             price=MediaPrice(usd=0.014, per=1_048_576))
    check_image(images, REQUEST, tmp_path / "shot.png")
    payload = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.deepinfra.com/v1/openai/images/generations"
    assert payload == {"model": "black-forest-labs/FLUX-2-klein-4b", "prompt": "a quiet train station at dawn",
                       "size": "1024x576", "n": 1, "response_format": "b64_json"}
    [charge] = images.generate(REQUEST, tmp_path / "again.png")
    assert charge.usd == 0.007875  # 0.5625 megapixels


def test_deepinfra_out_of_credit_points_to_the_config(tmp_path):
    images, _ = deepinfra(lambda r: httpx.Response(402, text="insufficient balance"))
    with pytest.raises(ImageError, match="out of credit .*config/media.yaml"):
        images.generate(REQUEST, tmp_path / "shot.png")
    images, _ = deepinfra(lambda r: httpx.Response(200, json={"data": []}))
    with pytest.raises(ImageError, match="no image"):
        images.generate(REQUEST, tmp_path / "shot.png")


def test_identity_changes_with_the_model_size_and_style():
    base, _ = deepinfra(lambda r: None)
    other, _ = deepinfra(lambda r: None, style_suffix="watercolour")
    bigger, _ = deepinfra(lambda r: None, width=1280, height=720)
    assert len({base.identity, other.identity, bigger.identity}) == 3


def test_the_live_profile_builds_cloudflare_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    images = media.image_for("live")
    assert isinstance(images, CloudflareWorkersAI) and images.price == MediaPrice(usd=0.00088)
    assert (images.width, images.height) == (1024, 576) and "acct" in images.url


@pytest.mark.live
@pytest.mark.parametrize("provider", ["cloudflare-images", "deepinfra-images"])
def test_live_image_provider_passes_conformance(provider, tmp_path):
    loaded = media.load_media_config()
    if not all(os.environ.get(var) for var in loaded.providers[provider].env.values()):
        pytest.skip(f"secrets for {provider} are not set")
    loaded.profiles["live"].image.provider = provider
    check_image(media.image_for("live", loaded), REQUEST, tmp_path / "shot.png")
