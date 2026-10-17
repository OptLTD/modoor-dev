from datetime import datetime
from zoneinfo import ZoneInfo

from modoor.engine.orm_adapter import parse_dt, parse_dt_bound
from modoor.engine.query import BUSINESS_TZ, QueryTerm, match_term_value

SH = ZoneInfo("Asia/Shanghai")


def test_date_only_bound_uses_shanghai_calendar_day():
    start = parse_dt_bound("2026-04-26")
    end = parse_dt_bound("2026-05-25", end=True)
    assert start == datetime(2026, 4, 26, tzinfo=SH)
    assert end == datetime(2026, 5, 25, 23, 59, 59, 999999, tzinfo=SH)
    # 上海 5 月 26 日 0 点属于下一财务期间，不能被上期末日的 UTC 日界吃进去
    next_midnight = datetime(2026, 5, 26, tzinfo=SH)
    assert start <= next_midnight
    assert next_midnight > end


def test_naive_and_month_parse_use_business_tz():
    assert parse_dt("2026-05-26T00:00:00") == datetime(2026, 5, 26, tzinfo=BUSINESS_TZ)
    assert parse_dt("2026-05") == datetime(2026, 5, 1, tzinfo=BUSINESS_TZ)
    # 带偏移的时刻保持原时区，再比较时落到同一业务日
    utc = parse_dt("2026-05-25T16:00:00+00:00")
    assert utc is not None
    assert utc.astimezone(BUSINESS_TZ) == datetime(2026, 5, 26, tzinfo=BUSINESS_TZ)


def test_in_memory_date_match_uses_business_calendar_day():
    # 2026-05-25 16:00 UTC = 上海 5 月 26 日 0 点
    value = datetime(2026, 5, 25, 16, 0, tzinfo=ZoneInfo("UTC"))
    on_26 = QueryTerm("basic.utime", "BTW", ["2026-05-26", "2026-05-26"])
    on_25 = QueryTerm("basic.utime", "BTW", ["2026-05-25", "2026-05-25"])
    assert match_term_value(value, on_26)
    assert not match_term_value(value, on_25)
    assert match_term_value("2026-05-25T16:00:00Z", on_26)
    assert not match_term_value("2026-05-25T16:00:00Z", on_25)
