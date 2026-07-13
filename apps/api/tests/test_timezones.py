from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from dayboard.timezones import resolve_local_date_window, resolve_local_datetime


def test_resolve_local_datetime_uses_trusted_iana_timezone() -> None:
    resolved = resolve_local_datetime(datetime(2026, 7, 14, 12, 0), "Asia/Shanghai")

    assert resolved == datetime(2026, 7, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert resolved.isoformat() == "2026-07-14T12:00:00+08:00"


def test_resolve_local_datetime_rejects_existing_offset() -> None:
    with pytest.raises(ValueError, match="must not include"):
        resolve_local_datetime(
            datetime(2026, 7, 14, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            "Asia/Shanghai",
        )


def test_resolve_local_date_window_uses_inclusive_dates() -> None:
    start, end = resolve_local_date_window(
        date(2026, 7, 14),
        date(2026, 7, 15),
        "Asia/Shanghai",
    )

    assert start.isoformat() == "2026-07-14T00:00:00+08:00"
    assert end.isoformat() == "2026-07-16T00:00:00+08:00"
