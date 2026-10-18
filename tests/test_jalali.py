"""Shamsi date helpers: Gregorian -> Jalali with Tehran day boundary."""
from datetime import date, datetime

from bot.utils.timezone import jalali_date, jalali_datetime


def test_jalali_date_from_datetime():
    # 2024-03-20 is Nowruz: start of Jalali year 1403.
    assert jalali_date(datetime(2024, 3, 20, 12, 0)) == "1403/01/01"


def test_jalali_date_from_plain_date():
    assert jalali_date(date(2024, 3, 20)) == "1403/01/01"


def test_naive_utc_crosses_tehran_midnight():
    # 21:00 UTC is already 00:30 next day in Tehran (+03:30).
    assert jalali_date(datetime(2024, 3, 19, 21, 0)) == "1403/01/01"
    assert jalali_date(datetime(2024, 3, 19, 12, 0)) == "1402/12/29"


def test_none_is_dash():
    assert jalali_date(None) == "—"
    assert jalali_datetime(None) == "—"


def test_jalali_datetime_has_time():
    out = jalali_datetime(datetime(2024, 3, 20, 9, 0))
    assert out.startswith("1403/01/01")
    assert "ساعت" in out
