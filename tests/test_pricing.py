import time

import pytest

from bot.services import pricing as pricing_svc


TEST_MODELS = {
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
}

TEST_PLAN_TOKENS = {"BRONZE_MAX_TOKEN": 10000, "SILVER_MAX_TOKEN": 25000, "GOLD_MAX_TOKEN": 60000}


@pytest.fixture
def catalog(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", dict(TEST_MODELS))
    monkeypatch.setattr(settings, "BRONZE_MAX_TOKEN", TEST_PLAN_TOKENS["BRONZE_MAX_TOKEN"])
    monkeypatch.setattr(settings, "SILVER_MAX_TOKEN", TEST_PLAN_TOKENS["SILVER_MAX_TOKEN"])
    monkeypatch.setattr(settings, "GOLD_MAX_TOKEN", TEST_PLAN_TOKENS["GOLD_MAX_TOKEN"])
    yield


@pytest.fixture(autouse=True)
def fresh_cache():
    saved = dict(pricing_svc._cache)
    pricing_svc._cache.update({"rate": None, "at": 0.0})
    yield
    pricing_svc._cache.update(saved)


class _FakeResp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise Exception("http error")

    def json(self):
        return self._payload


class _FakeClient:
    calls = 0
    payload = {"status": 200, "data": {"currencies": {"USDT": {"price": 263600}}}}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        _FakeClient.calls += 1
        return _FakeResp(dict(_FakeClient.payload))


@pytest.fixture
def fake_http(monkeypatch):
    _FakeClient.calls = 0
    monkeypatch.setattr(pricing_svc.httpx, "AsyncClient", _FakeClient)
    return _FakeClient


def test_ceil_price_rounds_up_to_10k():
    assert pricing_svc.ceil_price(0) == 0
    assert pricing_svc.ceil_price(1) == 10000
    assert pricing_svc.ceil_price(79080) == 80000
    assert pricing_svc.ceil_price(197700) == 200000
    assert pricing_svc.ceil_price(474480) == 480000
    assert pricing_svc.ceil_price(80000) == 80000
    assert pricing_svc.ceil_price(80001) == 90000


def test_quality_breakdown_math(catalog):
    from bot.handlers import premium as premium_h

    # 10,000 tokens @ 200/443/1760 per image
    assert premium_h._quality_breakdown(10000) == "50 پایین | 22 متوسط | 5 بالا"
    assert premium_h._quality_breakdown(25000) == "125 پایین | 56 متوسط | 14 بالا"
    assert premium_h._quality_breakdown(60000) == "300 پایین | 135 متوسط | 34 بالا"


def test_quality_breakdown_text_lists_all_plans(catalog):
    from bot.handlers import premium as premium_h

    text = premium_h._quality_breakdown_text()
    assert "🥉" in text and "🥈" in text and "🥇" in text
    assert "50 پایین" in text


def test_fx_note_shows_cached_rate(catalog):
    import time as _time
    from bot.handlers import premium as premium_h

    pricing_svc._cache.update({"rate": 263600.0, "at": _time.monotonic()})
    note = premium_h._fx_note()
    assert note is not None
    assert "263,600" in note
    assert "۵ دقیقه" in note or "5 دقیقه" in note


def test_fx_note_hidden_without_rate(catalog):
    from bot.handlers import premium as premium_h

    assert premium_h._fx_note() is None
    assert premium_h._fx_note_text() == ""


def test_credits_used_math(catalog):
    from bot.services.models import credits_used, format_credits

    assert credits_used(500, 200) == 2.5
    assert credits_used(4000, 200) == 20.0
    assert credits_used(None, 200) is None
    assert credits_used(500, None) is None
    assert credits_used(0, 200) is None
    assert format_credits(20.0) == "20"
    assert format_credits(2.5) == "2.5"


def test_model_help_text(catalog):
    import bot.texts as texts

    assert "flare" in texts.MODEL_HELP
    assert "sunburst" in texts.MODEL_HELP
    assert "هم‌قیمت" in texts.MODEL_HELP
    assert "توکن" not in texts.MODEL_HELP
    assert "token" not in texts.MODEL_HELP.lower()


def test_images_per_quality_math(catalog):
    from bot.services.models import images_per_quality

    # user example: 20,000 tokens → 100 / 45 / 11
    assert images_per_quality(20000, "gpt-image-2.5-flare") == {
        "low": 100, "medium": 45, "high": 11,
    }
    assert images_per_quality(0, "gpt-image-2.5-flare") == {
        "low": 0, "medium": 0, "high": 0,
    }
    # unknown model estimates are skipped
    assert images_per_quality(20000, "unknown-model") == {}


def test_balance_template_renders_breakdown():
    import bot.texts as texts

    rendered = texts.QUOTA_REMAINING_TOKENS.format(
        tier="برنزی",
        model="gpt-image-2.5-flare",
        breakdown="• پایین: 100 تصویر\n• متوسط: 45 تصویر",
    )
    assert "100 تصویر" in rendered
    assert "توکن" not in rendered
    assert "token" not in rendered.lower()
    assert len(rendered) < 4096


def test_no_token_words_in_user_facing_texts():
    import bot.texts as texts

    bad = []
    for name in dir(texts):
        if name.startswith("__"):
            continue
        value = getattr(texts, name)
        if isinstance(value, str) and (
            "توکن" in value or "token" in value.lower()
        ):
            bad.append(name)
    assert bad == [], f"user-facing texts mention tokens: {bad}"


def test_plan_usd_cost(catalog):
    # 10,000 tokens @ $30/1M = $0.30 (not $3.00)
    assert pricing_svc.plan_usd_cost("bronze") == pytest.approx(0.30)
    assert pricing_svc.plan_usd_cost("silver") == pytest.approx(0.75)
    assert pricing_svc.plan_usd_cost("gold") == pytest.approx(1.80)
    assert pricing_svc.plan_usd_cost("free") is None
    assert pricing_svc.plan_usd_cost("unknown") is None


def test_per_million_cost_typo_spelling(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", {
        "m": {"free": True, "per_milion_token_cost": 30},
    })
    monkeypatch.setattr(settings, "BRONZE_MAX_TOKEN", 10000)
    from bot.services.models import model_per_million_cost
    assert model_per_million_cost("m") == 30.0
    assert pricing_svc.plan_usd_cost("bronze") == pytest.approx(0.30)


@pytest.mark.asyncio
async def test_refresh_caches_rate(fake_http):
    rate = await pricing_svc.refresh_fx_rate()
    assert rate == 263600
    assert _FakeClient.calls == 1

    # second call within TTL does not hit HTTP
    rate = await pricing_svc.refresh_fx_rate()
    assert rate == 263600
    assert _FakeClient.calls == 1

    # forced refresh refetches
    rate = await pricing_svc.refresh_fx_rate(force=True)
    assert rate == 263600
    assert _FakeClient.calls == 2


@pytest.mark.asyncio
async def test_refresh_failure_keeps_old_value(fake_http, monkeypatch):
    await pricing_svc.refresh_fx_rate()
    assert _FakeClient.calls == 1

    async def boom(self, url):
        _FakeClient.calls += 1
        raise Exception("network down")

    monkeypatch.setattr(_FakeClient, "get", boom)
    rate = await pricing_svc.refresh_fx_rate(force=True)
    assert rate == 263600
    assert pricing_svc._cache["rate"] == 263600


def test_plan_price_uses_cache_no_http(catalog, monkeypatch):
    # seed a fresh cache directly; any HTTP attempt blows up
    pricing_svc._cache.update({"rate": 100000.0, "at": time.monotonic()})

    def _no_http(*a, **k):
        raise AssertionError("must not fetch on purchase path")

    monkeypatch.setattr(pricing_svc.httpx, "AsyncClient", _no_http)

    # 0.30 USD * 100,000 = 30,000 → ceil to 10k
    assert pricing_svc.plan_price_toman("bronze") == 30000
    # 0.75 * 100,000 = 75,000 → ceil to 10k
    assert pricing_svc.plan_price_toman("silver") == 80000
    # 1.80 * 100,000 = 180,000 → already a multiple of 10k
    assert pricing_svc.plan_price_toman("gold") == 180000


def test_plan_price_rounds_up(catalog):
    pricing_svc._cache.update({"rate": 8377.0, "at": time.monotonic()})
    # 0.30 * 8377 = 2513.1 → 10000
    assert pricing_svc.plan_price_toman("bronze") == 10000


def test_plan_price_none_when_uncomputable(catalog):
    # empty cache → None (never sell at a guessed price)
    assert pricing_svc.plan_price_toman("bronze") is None
    assert pricing_svc.plan_price_toman("unknown") is None


def test_plan_price_none_without_cost_data(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", {"bare-model": {"free": True}})
    monkeypatch.setattr(
        settings, "BRONZE_MAX_TOKEN", 10000
    )
    import time as _time
    pricing_svc._cache.update({"rate": 100000.0, "at": _time.monotonic()})
    assert pricing_svc.plan_price_toman("bronze") is None


def test_purchase_blocked_without_price(monkeypatch):
    from bot.config import settings
    from bot.services.payment import _plan_amount
    monkeypatch.setattr(settings, "MODELS", {"bare-model": {"free": True}})
    monkeypatch.setattr(settings, "BRONZE_MAX_TOKEN", 10000)
    with pytest.raises(ValueError):
        _plan_amount("bronze")
