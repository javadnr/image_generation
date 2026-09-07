import base64
from openai import AsyncOpenAI
from bot.config import settings

TIER_MODELS = {
    "free": settings.FREE_MODEL,
    "bronze": settings.BRONZE_MODEL,
    "silver": settings.SILVER_MODEL,
    "gold": settings.GOLD_MODEL,
}

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_image(prompt: str, tier: str, width: int = 1024, height: int = 1024) -> bytes:
    model = TIER_MODELS[tier]
    result = await client.images.generate(
        model=model,
        prompt=prompt,
        size=f"{width}x{height}",
        n=1,
    )
    return base64.b64decode(result.data[0].b64_json)


async def edit_image(file_path: str, prompt: str, tier: str, width: int = 1024, height: int = 1024) -> bytes:
    model = TIER_MODELS[tier]
    with open(file_path, "rb") as f:
        result = await client.images.edit(
            model=model,
            image=[f],
            prompt=prompt,
            size=f"{width}x{height}",
        )
    return base64.b64decode(result.data[0].b64_json)
