"""Query operator helpers — aligned with option-library/search (worth-compatible)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


@dataclass
class QueryTerm:
    field: str
    op: str  # EQ|IN|NE|BTW|NIL|NNL|RCT|FTR|LIKE|GT|GE|LT|LE|GTE|LTE
    value: Any
    group: str = ""  # "" = AND; "or" = OR group (charts.json logic: OR / GROUP:OR)


def query_field_key(key: str) -> str:
    """``basic.utime:BTW`` → ``basic.utime``; bare keys unchanged."""
    k = str(key or "")
    if ":" in k:
        return k.rsplit(":", 1)[0]
    return k


def merge_search_query(
    base: dict[str, Any] | None,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge view default query with caller query.

    When the caller filters a field (any operator), drop all default terms on
    that same field so e.g. ``RCT CURRENT_MONTH`` does not AND with an
    explicit ``BTW`` range.
    """
    out = dict(base or {})
    if not override:
        return out
    touched = {query_field_key(k) for k in override}
    for k in list(out):
        if query_field_key(k) in touched:
            del out[k]
    out.update(override)
    return out


def _today_local() -> date:
    # Keep date-only BTW bounds; local calendar matches option-library day anchor.
    return datetime.now().astimezone().date()


def _add_months(d: date, months: int) -> date:
    """Calendar month shift (same idea as Go time.Time.AddDate(0, months, 0))."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # clamp day for shorter months
    for day in range(d.day, 0, -1):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 1)


# Financial period (timeTerm): default financial period cutover day-of-month.
_TIME_TERM_START = 26


def _clamp_term_start(start: int) -> int:
    return start if 1 <= int(start) <= 28 else 26


def _uterm_of(day: date, *, start: int = _TIME_TERM_START) -> int:
    """YYYYMM financial period containing ``day`` (cutover on ``start``)."""
    day_start = _clamp_term_start(start)
    y, m, d = day.year, day.month, day.day
    if d < day_start:
        return y * 100 + m
    m += 1
    if m > 12:
        y += 1
        m = 1
    return y * 100 + m


def _prev_uterm(uterm: int) -> int:
    y, m = divmod(int(uterm), 100)
    m -= 1
    if m < 1:
        y -= 1
        m = 12
    return y * 100 + m


def _term_date_bounds(uterm: int, *, start: int = _TIME_TERM_START) -> tuple[str, str]:
    """Inclusive calendar bounds [start, end] as YYYY-MM-DD for a YYYYMM term."""
    day_start = _clamp_term_start(start)
    y, m = divmod(int(uterm), 100)
    if m <= 1:
        sy, sm = y - 1, 12
    else:
        sy, sm = y, m - 1
    start_d = date(sy, sm, day_start)
    end_d = date(y, m, day_start) - timedelta(days=1)
    return start_d.isoformat(), end_d.isoformat()


def _week_bounds(today: date, *, previous: bool = False) -> tuple[date, date]:
    # Monday-start week (option-library: weekday Sunday=7)
    wd = today.isoweekday()  # Mon=1 .. Sun=7
    week_start = today - timedelta(days=wd - 1)
    if previous:
        week_start = week_start - timedelta(days=7)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _month_bounds(today: date, *, previous: bool = False) -> tuple[date, date]:
    if previous:
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev, last_prev
    first = today.replace(day=1)
    if first.month == 12:
        nxt = date(first.year + 1, 1, 1)
    else:
        nxt = date(first.year, first.month + 1, 1)
    return first, nxt - timedelta(days=1)


def _year_bounds(today: date, *, previous: bool = False) -> tuple[date, date]:
    y = today.year - 1 if previous else today.year
    return date(y, 1, 1), date(y, 12, 31)


def _recent_range(token: str) -> tuple[str, str]:
    """
    Expand RCT/FTR token → inclusive date bounds (YYYY-MM-DD).

    Token names & intent from option-library/search/schema/query.go.
    """
    today = _today_local()
    token = str(token or "").strip().upper()

    if token == "CURRENT_WEEK":
        a, b = _week_bounds(today)
        return a.isoformat(), b.isoformat()
    if token == "PREVIOUS_WEEK":
        a, b = _week_bounds(today, previous=True)
        return a.isoformat(), b.isoformat()
    if token == "CURRENT_MONTH":
        a, b = _month_bounds(today)
        return a.isoformat(), b.isoformat()
    if token == "PREVIOUS_MONTH":
        a, b = _month_bounds(today, previous=True)
        return a.isoformat(), b.isoformat()
    if token == "CURRENT_YEAR":
        a, b = _year_bounds(today)
        return a.isoformat(), b.isoformat()
    if token == "PREVIOUS_YEAR":
        a, b = _year_bounds(today, previous=True)
        return a.isoformat(), b.isoformat()

    # Financial terms (timeTerm cutover day, default 26): expand to date BTW on utime-like fields.
    if token == "CURRENT_TERM":
        return _term_date_bounds(_uterm_of(today))
    if token == "PREVIOUS_TERM":
        return _term_date_bounds(_prev_uterm(_uterm_of(today)))

    # RECENT_* — from today back
    recent_days = {
        "RECENT_3_DAYS": 3,
        "RECENT_1_WEEK": 7,
        "RECENT_2_WEEK": 14,
    }
    if token in recent_days:
        start = today - timedelta(days=recent_days[token])
        return start.isoformat(), today.isoformat()

    recent_months = {
        "RECENT_1_MONTH": 1,
        "RECENT_2_MONTH": 2,
        "RECENT_3_MONTH": 3,
        "RECENT_6_MONTH": 6,
    }
    if token in recent_months:
        start = _add_months(today, -recent_months[token])
        return start.isoformat(), today.isoformat()

    # FUTURE_* — from today forward
    future_days = {
        "FUTURE_1_WEEK": 7,
        "FUTURE_2_WEEK": 14,
    }
    if token in future_days:
        end = today + timedelta(days=future_days[token])
        return today.isoformat(), end.isoformat()

    future_months = {
        "FUTURE_1_MONTH": 1,
        "FUTURE_2_MONTH": 2,
        "FUTURE_3_MONTH": 3,
        "FUTURE_6_MONTH": 6,
    }
    if token in future_months:
        end = _add_months(today, future_months[token])
        return today.isoformat(), end.isoformat()

    # default: recent 30 days
    start = today - timedelta(days=30)
    return start.isoformat(), today.isoformat()


def _normalize_op(op: str) -> str:
    """Accept option-library GE/LE; map GTE/LTE → GE/LE for SQL adapters."""
    if op == "GTE":
        return "GE"
    if op == "LTE":
        return "LE"
    return op


def parse_query(query: dict[str, Any] | None) -> list[QueryTerm]:
    if not query:
        return []
    terms: list[QueryTerm] = []
    for raw_key, value in query.items():
        key = str(raw_key)
        uk = key.upper()
        if uk == "GROUP:AND" or uk.startswith("GROUP:AND:"):
            nested = value if isinstance(value, dict) else {}
            for t in parse_query(nested):
                terms.append(t)
            continue
        if uk == "GROUP:OR" or uk.startswith("GROUP:OR:"):
            nested = value if isinstance(value, dict) else {}
            mode = "or" if uk == "GROUP:OR" else f"or:{key.split(':', 2)[-1]}"
            for t in parse_query(nested):
                t.group = mode or t.group
                terms.append(t)
            continue
        if ":" in key:
            field, op = key.rsplit(":", 1)
            op = op.upper()
        elif isinstance(value, dict) and len(value) == 1:
            # allow { "basic.team_id": { "IN": [1, 2] } }
            op_key, nested_val = next(iter(value.items()))
            field, op, value = key, str(op_key).upper(), nested_val
        else:
            field, op = key, "EQ"
        op = _normalize_op(op)
        if op in ("RCT", "FTR"):
            a, b = _recent_range(str(value))
            terms.append(QueryTerm(field=field, op="BTW", value=[a, b]))
            continue
        # Adapters historically match GTE/LTE — keep wire format GE→GTE for SQL layer
        if op == "GE":
            op = "GTE"
        elif op == "LE":
            op = "LTE"
        terms.append(QueryTerm(field=field, op=op, value=value))
    return terms


def _dateish_key(val: Any) -> str | None:
    """Normalize datetime/date-ish values to YYYY-MM-DD for inclusive day compares."""
    if val in (None, ""):
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    s = str(val).strip()
    if not s:
        return None
    # ISO / datetime-local: take calendar day
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


def match_term_value(val: Any, term: QueryTerm) -> bool:
    """In-memory match for JSON-document adapters (freight etc.)."""
    op = term.op
    want = term.value
    if op == "EQ":
        if val in (None, "") and want in (None, ""):
            return True
        return val == want
    if op == "NE":
        return val != want
    if op == "IN":
        wanted = want if isinstance(want, list) else [want]
        # 多选字段存的是列表：包含任一即可，不要拿整表去比。
        if isinstance(val, list):
            return any(item in wanted for item in val)
        return val in wanted
    if op == "LIKE":
        return str(want).lower() in str(val or "").lower()
    if op == "NIL":
        empty = val in (None, "")
        return empty if want in (True, "true", 1, "1") else not empty
    if op == "NNL":
        return val not in (None, "")
    if op in ("GT", "GTE", "LT", "LTE", "BTW"):
        left = _dateish_key(val)
        if left is None:
            return False
        try:
            if op == "BTW" and isinstance(want, (list, tuple)) and len(want) >= 2:
                lo = _dateish_key(want[0]) or ""
                hi = _dateish_key(want[1]) or ""
                return lo <= left <= hi
            right = _dateish_key(want)
            if right is None:
                return False
            if op == "GT":
                return left > right
            if op == "GTE":
                return left >= right
            if op == "LT":
                return left < right
            if op == "LTE":
                return left <= right
        except Exception:  # noqa: BLE001
            return False
        return False
    # unsupported ops — do not exclude
    return True
