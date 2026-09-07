import base64
import logging
from openai import AsyncOpenAI
from bot.config import settings

log = logging.getLogger(__name__)

TIER_MODELS = {
    "free": settings.FREE_MODEL,
    "bronze": settings.BRONZE_MODEL,
    "silver": settings.SILVER_MODEL,
    "gold": settings.GOLD_MODEL,
}

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_image(prompt: str, tier: str, width: int = 1024, height: int = 1024) -> bytes:
    model = TIER_MODELS[tier]
    log.info("Generating image: model=%s size=%dx%d prompt=%s", model, width, height, prompt[:80])
    result = await client.images.generate(
        model=model,
        prompt=prompt,
        size=f"{width}x{height}",
        n=1,
    )
    img = result.data[0]
    usage = getattr(result, "usage", None)
    log.info(
        "Image generated: model=%s size=%dx%d tokens=%s",
        model, width, height, usage.get("total_tokens") if isinstance(usage, dict) else usage,
    )
    return base64.b64decode(img.b64_json)


async def edit_image(file_path: str, prompt: str, tier: str, width: int = 1024, height: int = 1024) -> bytes:
    model = TIER_MODELS[tier]
    log.info("Editing image: model=%s size=%dx%d file=%s prompt=%s", model, width, height, file_path, prompt[:80])
    with open(file_path, "rb") as f:
        result = await client.images.edit(
            model=model,
            image=f,
            prompt=prompt,
            size=f"{width}x{height}",
        )
    img = result.data[0]
    usage = getattr(result, "usage", None)
    log.info(
        "Image edited: model=%s size=%dx%d tokens=%s",
        model, width, height, usage.get("total_tokens") if isinstance(usage, dict) else usage,
    )
    return base64.b64decode(img.b64_json)
