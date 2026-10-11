import time

import pytest

from bot.services import pricing as pricing_svc


TEST_MODELS = {
    "gpt-image-2.5-flare": {
        "label": "gpt-image-2.5-flare",
        "free": True,
        "per_million_cost": 30,
        "cost": {"low": {"cost": 0.006, "tokens": 200}},
    },
}

TEST_PLAN_TOKENS = {"bronze": 10000, "silver": 25000, "gold": 60000}


@pytest.fixture
def catalog(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", dict(TEST_MODELS))
    monkeypatch.setattr(settings, "PLAN_TOKENS", dict(TEST_PLAN_TOKENS))
    monkeypatch.setattr(settings, "BRONZE_PRICE", 99000)
    monkeypatch.setattr(settings, "SILVER_PRICE", 199000)
    monkeypatch.setattr(settings, "GOLD_PRICE", 399000)
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


def test_ceil_to_10():
    assert pricing_svc.ceil_to_10(251) == 260
    assert pricing_svc.ceil_to_10(264) == 270
    assert pricing_svc.ceil_to_10(270) == 270
    assert pricing_svc.ceil_to_10(0) == 0
    assert pricing_svc.ceil_to_10(1) == 10
    assert pricing_svc.ceil_to_10(30000) == 30000


def test_plan_usd_cost(catalog):
    # 10,000 tokens @ $30/1M = $0.30 (not $3.00)
    assert pricing_svc.plan_usd_cost("bronze") == pytest.approx(0.30)
    assert pricing_svc.plan_usd_cost("silver") == pytest.approx(0.75)
    assert pricing_svc.plan_usd_cost("gold") == pytest.approx(1.80)
    assert pricing_svc.plan_usd_cost("free") is None
    assert pricing_svc.plan_usd_cost("unknown") is None


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

    # 0.30 USD * 100,000 = 30,000 → already a multiple of 10
    assert pricing_svc.plan_price_toman("bronze") == 30000
    # 0.75 * 100,000 = 75,000
    assert pricing_svc.plan_price_toman("silver") == 75000
    # 1.80 * 100,000 = 180,000
    assert pricing_svc.plan_price_toman("gold") == 180000


def test_plan_price_rounds_up(catalog):
    pricing_svc._cache.update({"rate": 8377.0, "at": time.monotonic()})
    # 0.30 * 8377 = 2513.1 → 2520
    assert pricing_svc.plan_price_toman("bronze") == 2520


def test_plan_price_falls_back_to_static(catalog):
    # empty cache and no cost data → static *_PRICE
    assert pricing_svc.plan_price_toman("bronze") == 99000
    assert pricing_svc.plan_price_toman("silver") == 199000
    assert pricing_svc.plan_price_toman("gold") == 399000
    assert pricing_svc.plan_price_toman("unknown") == 0
