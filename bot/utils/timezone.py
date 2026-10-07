from datetime import date, datetime, timedelta

import pytz

IRAN_TZ = pytz.timezone("Asia/Tehran")


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
