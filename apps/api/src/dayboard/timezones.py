from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def timezone_info(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {timezone}") from exc


def resolve_local_datetime(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is not None:
        raise ValueError("Local datetime must not include a timezone offset")
    return value.replace(tzinfo=timezone_info(timezone))


def resolve_local_date_window(
    start_date: date,
    end_date: date,
    timezone: str,
) -> tuple[datetime, datetime]:
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    zone = timezone_info(timezone)
    return (
        datetime.combine(start_date, time.min, tzinfo=zone),
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone),
    )
