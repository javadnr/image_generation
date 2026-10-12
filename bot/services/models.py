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

Profit (PROFIT_PERCENTAGE) is applied exactly once, at charge/display
time, on top of raw estimates or actual API usage. All helpers below
round float artifacts away before ceil/floor so boundary values are exact.
"""
import math

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


def edits_available(balance: int, edit_cost: int | None) -> int:
    """Whole image edits affordable (floor division, partial edits impossible)."""
    if not edit_cost or edit_cost <= 0:
        return 0
    return max(0, (balance or 0)) // edit_cost


def profit_rate() -> float:
    """1 + PROFIT_PERCENTAGE/100. 1.0 when unconfigured or invalid."""
    try:
        return 1.0 + float(settings.PROFIT_PERCENTAGE or 0) / 100
    except (TypeError, ValueError):
        return 1.0


def _ceil(value: float) -> int:
    return math.ceil(round(value, 6))


def effective_estimate(model_id: str | None, quality: str | None) -> int | None:
    """Profit-inclusive estimated tokens per image. None when unknown."""
    estimate = estimate_tokens(model_id, quality)
    if not estimate:
        return None
    return _ceil(estimate * profit_rate())


def charge_for(actual_tokens: int | None) -> int:
    """Token charge for actual API usage, profit applied exactly once."""
    if not actual_tokens:
        return 0
    return _ceil(actual_tokens * profit_rate())


def images_per_quality(balance: int, model_id: str | None) -> dict:
    """Approximate remaining images per quality (floor division).

    Uses profit-inclusive estimates. Qualities with unknown estimates are
    skipped. Counts are estimates — actual consumption varies per generation.
    """
    model = model_id or default_model()
    out = {}
    for quality in QUALITY_ORDER:
        effective = effective_estimate(model, quality)
        if effective:
            out[quality] = (balance or 0) // effective
    return out


def used_credits(actual_tokens: int | None, low_effective: int | None) -> int | None:
    """Whole image credits consumed, rounded up. None when unknown."""
    if not actual_tokens or not low_effective:
        return None
    charged = charge_for(actual_tokens)
    return -(-charged // low_effective)


def credit_usage(
    balance_before: int, actual_tokens: int | None, model_id: str | None
) -> tuple[int | None, int | None]:
    """(used_credits, remaining_images) for result captions.

    Both derived from the pre-deduction balance and actual API usage,
    so captions predict exactly what deduct_tokens will produce.
    """
    low_effective = effective_estimate(model_id or default_model(), "low")
    if low_effective is None or actual_tokens is None:
        return None, None
    charged = charge_for(actual_tokens)
    used = -(-charged // low_effective)
    remaining = max(0, (balance_before or 0) - charged) // low_effective
    return used, remaining


def plan_allowance(plan: str) -> int:
    """Token allowance granted by a plan (BRONZE/SILVER/GOLD_MAX_TOKEN)."""
    return {
        "bronze": settings.BRONZE_MAX_TOKEN,
        "silver": settings.SILVER_MAX_TOKEN,
        "gold": settings.GOLD_MAX_TOKEN,
    }.get(plan, 0)
