"""Dynamic plan pricing from token allowances.

Price chain (all driven by .env data, no hardcoding):

    plan tokens (PLAN_TOKENS)
      × model per_million_cost (MODELS) / 1_000_000
      = USD cost
      × cached USDT/Toman rate (Tetherland, refreshed every 5 min)
      = Toman price, rounded UP to the nearest 10

The exchange rate is NEVER fetched on the purchase path: a background
task refreshes the cache every FX_TTL_SECONDS, and all price getters read
the cache synchronously. When the rate or cost data is missing, the price
is None and the purchase is blocked — there are no hardcoded prices.
"""
import asyncio
import logging
import math
import time

import httpx

from bot.services.models import default_model

logger = logging.getLogger(__name__)

FX_URL = "https://api.tetherland.com/currencies"
FX_TTL_SECONDS = 300

_cache: dict = {"rate": None, "at": 0.0}
_lock = asyncio.Lock()


def ceil_to_10(amount) -> int:
    """Round up to the nearest multiple of 10: 251->260, 264->270, 270->270."""
    return int(math.ceil(float(amount) / 10) * 10)


def cached_rate() -> float | None:
    if _cache["rate"] and (time.monotonic() - _cache["at"]) < FX_TTL_SECONDS:
        return _cache["rate"]
    return None


def last_known_rate() -> float | None:
    """Most recent rate even if stale (for display). None if never fetched."""
    return _cache["rate"]


async def refresh_fx_rate(force: bool = False) -> float | None:
    """Fetch the USDT/Toman rate unless the cache is fresh (unless forced)."""
    async with _lock:
        if not force and cached_rate() is not None:
            return _cache["rate"]
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                resp = await client.get(FX_URL)
                resp.raise_for_status()
                data = resp.json()
            rate = float(data["data"]["currencies"]["USDT"]["price"])
            if rate <= 0:
                raise ValueError(f"Invalid rate: {rate}")
            _cache["rate"] = rate
            _cache["at"] = time.monotonic()
            logger.info("FX rate refreshed: 1 USDT = %s Toman", rate)
        except Exception:
            logger.exception("FX rate refresh failed; keeping previous value")
        return _cache["rate"]


async def fx_loop() -> None:
    """Background task: keep the cached rate fresh every 5 minutes."""
    await refresh_fx_rate()
    while True:
        await asyncio.sleep(FX_TTL_SECONDS)
        await refresh_fx_rate(force=True)


def plan_usd_cost(plan: str) -> float | None:
    """USD cost of a plan allowance at the default model's per-million rate."""
    from bot.services.models import plan_allowance, model_per_million_cost, default_model

    allowance = plan_allowance(plan)
    per_million = model_per_million_cost(default_model())
    if not allowance or not per_million:
        return None
    try:
        return allowance * float(per_million) / 1_000_000
    except (TypeError, ValueError):
        return None


def plan_price_toman(plan: str) -> int | None:
    """Plan price in Tomans, rounded up to 10.

    Returns None when the price cannot be computed (missing cost data or
    no cached FX rate). Callers must not sell at None — block the purchase.
    """
    usd = plan_usd_cost(plan)
    rate = _cache["rate"]
    if usd is None or not rate:
        logger.warning("Cannot price plan %s (usd=%s rate=%s)", plan, usd, rate)
        return None
    return ceil_to_10(usd * rate)
