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
        "cost": {
            "low": {"cost": 0.006, "tokens": 200},
            "medium": {"cost": 0.0133, "tokens": 443},
            "high": {"cost": 0.0266, "tokens": 1760},
        },
    },
    "gpt-image-2.5-sunburst": {
        "label": "gpt-image-2.5-sunburst",
        "free": False,
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


def plan_allowance(plan: str) -> int:
    """Token allowance granted by a plan. 0 when unconfigured."""
    try:
        return int(settings.PLAN_TOKENS.get(plan, 0))
    except (TypeError, ValueError):
        return 0
