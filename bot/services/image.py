import base64
import logging
import httpx
from openai import AsyncOpenAI
from bot.config import settings

log = logging.getLogger(__name__)

TIER_MODELS = {
    "free": settings.FREE_MODEL,
    "bronze": settings.BRONZE_MODEL,
    "silver": settings.SILVER_MODEL,
    "gold": settings.GOLD_MODEL,
}

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL or None,
)


async def _extract_image_bytes(img) -> bytes:
    """Compatible endpoints may return b64_json or a url — handle both."""
    if getattr(img, "b64_json", None):
        return base64.b64decode(img.b64_json)
    if getattr(img, "url", None):
        log.info("Downloading image from url: %s", img.url[:80])
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
            resp = await http.get(img.url)
            resp.raise_for_status()
            return resp.content
    raise ValueError("Image response contained neither b64_json nor url")


def _extract_tokens(result) -> int | None:
    usage = getattr(result, "usage", None)
    tokens = usage.get("total_tokens") if isinstance(usage, dict) else usage
    return tokens if isinstance(tokens, int) else None


async def generate_image(prompt: str, tier: str, width: int = 1024, height: int = 1024) -> tuple[bytes, int | None]:
    model = TIER_MODELS[tier]
    log.info("Generating image: model=%s size=%dx%d prompt=%s", model, width, height, prompt[:80])
    result = await client.images.generate(
        model=model,
        prompt=prompt,
        size=f"{width}x{height}",
        quality="low",
        n=1,
    )
    img = result.data[0]
    tokens = _extract_tokens(result)
    log.info(
        "Image generated: model=%s size=%dx%d tokens=%s",
        model, width, height, tokens,
    )
    return await _extract_image_bytes(img), tokens
