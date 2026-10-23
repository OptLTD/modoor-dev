"""Daily job clock parsing and due checks."""

from datetime import datetime
from zoneinfo import ZoneInfo

from modoor.platform.loader import parse_daily_clock
from modoor.runtime.worker import daily_job_due

TZ = ZoneInfo("Asia/Shanghai")


def test_parse_daily_clock():
    assert parse_daily_clock("00:10") == "00:10"
    assert parse_daily_clock("2:5") == "02:05"
    assert parse_daily_clock("24:00") is None
    assert parse_daily_clock("noon") is None
    assert parse_daily_clock("") is None


def test_daily_job_due_waits_until_clock_then_once_per_day():
    early = datetime(2026, 10, 23, 0, 9, tzinfo=TZ)
    assert daily_job_due(early, "00:10", None) is False

    at = datetime(2026, 10, 23, 0, 10, tzinfo=TZ)
    assert daily_job_due(at, "00:10", None) is True
    assert daily_job_due(at, "00:10", "2026-10-22") is True
    assert daily_job_due(at, "00:10", "2026-10-23") is False

    later = datetime(2026, 10, 23, 15, 0, tzinfo=TZ)
    assert daily_job_due(later, "00:10", None) is True
    assert daily_job_due(later, "00:10", "2026-10-23") is False
