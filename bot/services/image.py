import base64
import logging
import httpx
from openai import AsyncOpenAI
from bot.config import settings
from bot.services.models import default_model

log = logging.getLogger(__name__)

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


async def generate_image(prompt: str, tier: str, width: int = 1024, height: int = 1024, quality: str = "low", model: str | None = None) -> tuple[bytes, int | None]:
    from bot.services.models import default_model
    model = model or default_model()
    log.info("Generating image: model=%s size=%dx%d quality=%s prompt=%s", model, width, height, quality, prompt[:80])
    result = await client.images.generate(
        model=model,
        prompt=prompt,
        size=f"{width}x{height}",
        quality=quality,
        n=1,
    )
    img = result.data[0]
    tokens = _extract_tokens(result)
    log.info(
        "Image generated: model=%s size=%dx%d tokens=%s",
        model, width, height, tokens,
    )
    return await _extract_image_bytes(img), tokens


async def edit_image(
    file_path: str,
    prompt: str,
    model: str | None = None,
    size: str | None = None,
) -> tuple[bytes, int | None]:
    # NOTE: `quality` is intentionally NOT passed: the pinned SDK rejects it
    # on edit() (proven TypeError in production logs), so sending it would
    # break every edit. Size is a supported edit parameter.
    model = model or default_model()
    log.info("Editing image: model=%s size=%s file=%s prompt=%s", model, size, file_path, prompt[:80])
    edit_kwargs = {"model": model, "prompt": prompt}
    if size is not None:
        edit_kwargs["size"] = size
    with open(file_path, "rb") as f:
        result = await client.images.edit(image=f, **edit_kwargs)
    img = result.data[0]
    tokens = _extract_tokens(result)
    log.info("Image edited: model=%s tokens=%s", model, tokens)
    return await _extract_image_bytes(img), tokens
