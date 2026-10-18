from datetime import date, datetime, timedelta

import jdatetime
import pytz

IRAN_TZ = pytz.timezone("Asia/Tehran")


def _tehran(dt: datetime) -> datetime:
    """Timestamps are stored as naive UTC; return a Tehran-aware datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    return dt.astimezone(IRAN_TZ)


def jalali_date(dt) -> str:
    """Shamsi date (YYYY/MM/DD) for a naive-UTC datetime, date, or None."""
    if not dt:
        return "—"
    try:
        d = _tehran(dt).date() if isinstance(dt, datetime) else dt
        return jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d")
    except Exception:
        return dt.strftime("%Y/%m/%d")


def jalali_datetime(dt) -> str:
    """Shamsi date + Tehran time, e.g. 1403/07/27 ساعت 18:30."""
    if not dt:
        return "—"
    try:
        local = _tehran(dt).replace(tzinfo=None) if isinstance(dt, datetime) else dt
        return jdatetime.datetime.fromgregorian(datetime=local).strftime("%Y/%m/%d ساعت %H:%M")
    except Exception:
        return dt.strftime("%Y/%m/%d %H:%M")


def tehran_day_utc_window(day: date) -> tuple[datetime, datetime]:
    """Return naive-UTC (start, end) datetimes bounding a Tehran calendar day.

    Event timestamps are stored as naive UTC, so analytics queries compare
    against this window instead of func.date(), which would use the DB
    server timezone.
    """
    start_local = IRAN_TZ.localize(datetime(day.year, day.month, day.day))
    end_local = IRAN_TZ.localize(datetime(day.year, day.month, day.day) + timedelta(days=1))
    return (
        start_local.astimezone(pytz.utc).replace(tzinfo=None),
        end_local.astimezone(pytz.utc).replace(tzinfo=None),
    )


def today_in_tehran() -> date:
    return datetime.now(IRAN_TZ).date()
