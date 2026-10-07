"""Minimal cron helpers for flow schedules (5-field cron)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _match(field: str, value: int) -> bool:
    field = (field or "*").strip()
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError:
                continue
            if step > 0 and value % step == 0:
                return True
        elif "-" in part:
            a, b = part.split("-", 1)
            try:
                if int(a) <= value <= int(b):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                continue
    return False


def cron_matches(cron: str, when: datetime) -> bool:
    """Match standard 5-field cron: min hour dom month dow (0=Sun)."""
    parts = (cron or "").strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    return (
        _match(minute, when.minute)
        and _match(hour, when.hour)
        and _match(dom, when.day)
        and _match(month, when.month)
        and _match(dow, when.isoweekday() % 7)
    )


def next_cron_time(cron: str, *, after: datetime | None = None) -> datetime | None:
    """Brute-force next minute match within 8 days."""
    parts = (cron or "").strip().split()
    if len(parts) != 5:
        return None
    cursor = after or datetime.now(timezone.utc)
    if cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=timezone.utc)
    cursor = cursor.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 8):
        if cron_matches(cron, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    return None
