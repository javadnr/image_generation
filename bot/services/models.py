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

IMAGE_SIZES maps aspect-ratio keys to API pixel dimensions. Sizes are
sent to the image API exactly as configured here — if a model rejects a
ratio, the failure surfaces through the normal error path instead of
silently substituting a different size.

The image API only accepts sizes where both sides are multiples of 16
and at least 1024px; every entry must satisfy that.
"""
IMAGE_SIZES = {
    "square": {"label": "مربع (۱:۱)", "width": 1024, "height": 1024},
    "portrait": {"label": "عمودی (۳:۴)", "width": 1024, "height": 1344},
    "story": {"label": "استوری (۹:۱۶)", "width": 1024, "height": 1792},
    "landscape": {"label": "افقی (۴:۳)", "width": 1344, "height": 1024},
    "widescreen": {"label": "عریض (۱۶:۹)", "width": 1792, "height": 1024},
}
DEFAULT_IMAGE_SIZE = "square"
VALID_IMAGE_SIZES = tuple(IMAGE_SIZES)

# Free users are pinned to this ratio; every other size is premium-only.
FREE_IMAGE_SIZE = "story"


def size_allowed(tier: str, size: str) -> bool:
    return tier != "free" or size == FREE_IMAGE_SIZE


def effective_size(tier: str, size: str | None) -> str:
    """Size actually used for a tier; free users always get FREE_IMAGE_SIZE."""
    if tier == "free":
        return FREE_IMAGE_SIZE
    return size or DEFAULT_IMAGE_SIZE


def size_label(key: str | None) -> str:
    return IMAGE_SIZES.get(key or "", {}).get("label") or key or DEFAULT_IMAGE_SIZE


def image_dimensions(key: str | None) -> tuple:
    """Pixel (width, height) for an aspect key. Raises on unknown keys
    so unsupported ratios fail explicitly instead of silently changing."""
    try:
        entry = IMAGE_SIZES[key or ""]
    except KeyError:
        raise ValueError(f"Unsupported image size: {key!r}")
    return entry["width"], entry["height"]


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


def capped_charge(balance: int, actual_tokens: int | None) -> tuple:
    """(charge, deducted) for one request against a balance.

    The charge keeps the real API cost (profit included) for admin
    reporting; the deduction never exceeds what the user actually has.
    """
    charged = charge_for(actual_tokens)
    return charged, min(charged, max(0, balance or 0))


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


# Ordered paid plans (lowest -> highest). Single source of truth for
# every place that iterates plans (menus, stats, discounts, validation).
PLANS = ("bronze", "silver", "gold", "diamond")


def plan_enabled(plan: str) -> bool:
    """Whether a plan is offered, from its *_ENABLED env flag."""
    return bool(getattr(settings, f"{plan.upper()}_ENABLED", True))


def enabled_plans() -> tuple:
    """PLANS filtered by the env flags, in plan order."""
    return tuple(p for p in PLANS if plan_enabled(p))


def plan_allowance(plan: str) -> int:
    """Token allowance granted by a plan (BRONZE..DIAMOND_MAX_TOKEN)."""
    return {
        "bronze": settings.BRONZE_MAX_TOKEN,
        "silver": settings.SILVER_MAX_TOKEN,
        "gold": settings.GOLD_MAX_TOKEN,
        "diamond": settings.DIAMOND_MAX_TOKEN,
    }.get(plan, 0)


def plan_snapshot(plan: str) -> dict:
    """Limitations of a plan, captured at activation time.

    Active subscribers keep these values even if the .env changes later;
    the next purchase records the new values instead.
    """
    return {"tokens": plan_allowance(plan), "edit_cost": settings.IMAGE_EDIT_COST_TOKENS}
