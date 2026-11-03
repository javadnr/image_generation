import base64
import logging
import httpx
from bot.config import settings
from bot.services.models import default_model

log = logging.getLogger(__name__)

AVALAI_BASE_URL = (settings.OPENAI_BASE_URL or "https://api.avalai.ir/v1").rstrip("/")


def _auth_headers() -> dict[str, str]:
    api_key = settings.AVALAI_API_KEY or settings.OPENAI_API_KEY
    return {"Authorization": f"Bearer {api_key}"}


async def _extract_image_bytes_from_item(item: dict) -> bytes:
    """Avalai may return b64_json or a url — handle both."""
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        log.info("Downloading image from url: %s", item["url"][:80])
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
            resp = await http.get(item["url"])
            resp.raise_for_status()
            return resp.content
    raise ValueError("Image response contained neither b64_json nor url")


def _extract_tokens(result: dict) -> int | None:
    usage = result.get("usage")
    tokens = usage.get("total_tokens") if isinstance(usage, dict) else usage
    return tokens if isinstance(tokens, int) else None


async def generate_image(
    prompt: str,
    tier: str,
    width: int = 1024,
    height: int = 1024,
    quality: str = "low",
    model: str | None = None,
) -> tuple[bytes, int | None]:
    from bot.services.models import default_model

    model = model or default_model()
    url = f"{AVALAI_BASE_URL}/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "size": f"{width}x{height}",
        "quality": quality,
        "n": 1,
        "response_format": "b64_json",
    }
    log.info(
        "Generating image: model=%s size=%dx%d quality=%s prompt=%s",
        model, width, height, quality, prompt[:80],
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as http:
        resp = await http.post(url, headers=_auth_headers(), json=payload)
        resp.raise_for_status()
        result = resp.json()
    img = result["data"][0]
    tokens = _extract_tokens(result)
    log.info(
        "Image generated: model=%s size=%dx%d tokens=%s",
        model, width, height, tokens,
    )
    return await _extract_image_bytes_from_item(img), tokens


async def edit_image(
    file_path: str,
    prompt: str,
    model: str | None = None,
    size: str | None = None,
    quality: str = "low",
) -> tuple[bytes, int | None]:
    model = model or default_model()
    url = f"{AVALAI_BASE_URL}/images/edits"
    log.info(
        "Editing image: model=%s size=%s file=%s prompt=%s quality=%s",
        model, size, file_path, prompt[:80], quality,
    )
    data: dict = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
    }
    if size is not None:
        data["size"] = size
    if quality:
        data["quality"] = quality

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as http:
        with open(file_path, "rb") as f:
            files = {"image": ("image.png", f, "image/png")}
            resp = await http.post(url, headers=_auth_headers(), data=data, files=files)
        resp.raise_for_status()
        result = resp.json()
    img = result["data"][0]
    tokens = _extract_tokens(result)
    log.info("Image edited: model=%s tokens=%s", model, tokens)
    return await _extract_image_bytes_from_item(img), tokens
