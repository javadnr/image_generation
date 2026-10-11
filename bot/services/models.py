"""Model catalog driven by the MODELS setting (.env JSON).

Schema per model id:
    {
        "label": "Display name (optional, defaults to the model id)",
        "free": true | false (optional, default false — premium only),
        "cost": {  (optional, base cost table per quality)
            "low": {"cost": 0.006, "tokens": 200},
            "medium": {"cost": 0.0133, "tokens": 443},
            "high": {"cost": 0.0266, "tokens": 1760}
        }
    }

FALLBACK_MODELS keeps the bot working when MODELS is not configured.
"""
from bot.config import settings

FALLBACK_MODELS = {
    "gpt-image-2.5-flare": {
        "label": "gpt-image-2.5-flare",
        "free": True,
        "per_million_cost": 30,
        "cost": {
            "low": {"cost": 0.006, "tokens": 200},
            "medium": {"cost": 0.0133, "tokens": 443},
            "high": {"cost": 0.0266, "tokens": 1760},
        },
    },
    "gpt-image-2.5-sunburst": {
        "label": "gpt-image-2.5-sunburst",
        "free": False,
        "per_million_cost": 30,
    },
}


def models() -> dict:
    return settings.MODELS or FALLBACK_MODELS


def model_ids() -> list:
    return list(models().keys())


def model_label(model_id: str) -> str:
    return models().get(model_id, {}).get("label") or model_id


def is_free_model(model_id: str) -> bool:
    return bool(models().get(model_id, {}).get("free", False))


def model_per_million_cost(model_id: str) -> float | None:
    """USD per 1M output tokens. Accepts the known typo spelling too,
    since hand-edited .env data uses it."""
    entry = models().get(model_id, {})
    value = entry.get("per_million_cost", entry.get("per_milion_token_cost"))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def default_model() -> str:
    for model_id in models():
        if is_free_model(model_id):
            return model_id
    ids = model_ids()
    return ids[0] if ids else "gpt-image-2.5-flare"


def model_cost(model_id: str, quality: str) -> tuple:
    """Return (cost, tokens) for a model+quality, or (None, None) if unknown."""
    entry = models().get(model_id, {}).get("cost", {}).get(quality, {})
    return entry.get("cost"), entry.get("tokens")


def estimate_tokens(model_id: str | None, quality: str | None) -> int | None:
    """Estimated output tokens for a model+quality, or None if unknown."""
    _, tokens = model_cost(model_id or default_model(), quality or "low")
    return tokens if isinstance(tokens, int) else None


QUALITY_ORDER = ("low", "medium", "high")


def credits_used(actual_tokens: int | None, low_estimate: int | None) -> float | None:
    """Image-credit equivalent of actual output tokens.

    1 credit = estimated tokens of one Low-quality image. Returns None
    when either side is unknown.
    """
    if not actual_tokens or not low_estimate:
        return None
    return actual_tokens / low_estimate


def format_credits(value: float) -> str:
    """Compact display: 20 instead of 20.0, 2.5 stays 2.5."""
    return str(int(value)) if value == int(value) else f"{value:.1f}"


def edits_available(balance: int, edit_cost: int | None) -> int:
    """Whole image edits affordable (floor division, partial edits impossible)."""
    if not edit_cost or edit_cost <= 0:
        return 0
    return max(0, (balance or 0)) // edit_cost


def images_per_quality(balance: int, model_id: str | None) -> dict:
    """Approximate remaining images per quality (floor division).

    Qualities with unknown estimates are skipped. Counts are estimates —
    actual consumption varies per generation.
    """
    model = model_id or default_model()
    out = {}
    for quality in QUALITY_ORDER:
        estimate = estimate_tokens(model, quality)
        if estimate:
            out[quality] = balance // estimate
    return out


def plan_allowance(plan: str) -> int:
    """Token allowance granted by a plan (BRONZE/SILVER/GOLD_MAX_TOKEN)."""
    return {
        "bronze": settings.BRONZE_MAX_TOKEN,
        "silver": settings.SILVER_MAX_TOKEN,
        "gold": settings.GOLD_MAX_TOKEN,
    }.get(plan, 0)
