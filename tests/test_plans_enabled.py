from types import SimpleNamespace

from bot.config import settings
from bot.handlers.premium import premium_text
from bot.keyboards.inline import premium_menu
from bot.services.models import enabled_plans

PLAN_FLAGS = ("BRONZE_ENABLED", "SILVER_ENABLED", "GOLD_ENABLED", "DIAMOND_ENABLED")


def test_disabled_plan_is_hidden(monkeypatch):
    monkeypatch.setattr(settings, "DIAMOND_ENABLED", False)
    assert enabled_plans() == ("bronze", "silver", "gold")

    user = SimpleNamespace(tier="free")
    kb = premium_menu(user)
    callbacks = [row[0].callback_data for row in kb.inline_keyboard]
    assert callbacks == ["buy_bronze", "buy_silver", "buy_gold"]

    text = premium_text(user)
    assert "الماسی" not in text
    assert "برنزی" in text and "طلایی" in text


def test_all_plans_disabled(monkeypatch):
    for flag in PLAN_FLAGS:
        monkeypatch.setattr(settings, flag, False)

    user = SimpleNamespace(tier="free")
    assert enabled_plans() == ()
    assert premium_menu(user) is None
    assert "پلنی برای خرید موجود نیست" in premium_text(user)
