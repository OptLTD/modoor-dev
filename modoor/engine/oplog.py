"""Thin oplog registry: pure diff + optional writer hook (no builtin.base import)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx

OplogWriter = Callable[..., Any]
_writer: OplogWriter | None = None

_OPLOG_SKIP_KEYS = frozenset(
    {
        "basic.password",
        "password",
        "basic.utime",
        "updated_at",
        "created_at",
        "basic.updated_at",
        "basic.created_at",
    }
)


def set_oplog_writer(fn: OplogWriter | None) -> None:
    global _writer
    _writer = fn


def _jsonish(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): _jsonish(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_jsonish(v) for v in val]
    return str(val)


def diff_row_values(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    skip_keys: frozenset[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Field-level diff ``{key: {old, new}}`` for audit (INSERT/UPDATE/DELETE)."""
    skip = skip_keys or _OPLOG_SKIP_KEYS
    left = before or {}
    right = after or {}
    keys = sorted(set(left) | set(right))
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        if key in skip:
            continue
        old = _jsonish(left.get(key))
        new = _jsonish(right.get(key))
        if old == new:
            continue
        out[key] = {"old": old, "new": new}
    return out


def record_oplog(session: Session, ctx: Ctx, **kwargs: Any) -> Any:
    """Delegate to the registered writer (e.g. builtin.base.domain.record_oplog)."""
    if _writer is None:
        return None
    return _writer(session, ctx, **kwargs)
