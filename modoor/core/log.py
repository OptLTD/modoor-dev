"""Developer logs for business writes. Bulk sync sets ctx.skip_oplog and stays quiet."""

from __future__ import annotations

import logging
from typing import Any

from modoor.core.ctx import Ctx

_logger = logging.getLogger("modoor.act")

_MAX_ITEMS = 30
_MAX_FIELDS = 8


def log(ctx: Ctx, event: str, **fields: Any) -> None:
    if getattr(ctx, "skip_oplog", False):
        return
    parts: list[str] = []
    for key, val in fields.items():
        text = _fmt(val)
        if not text:
            continue
        parts.append(f"{key}={text}")
    tail = (" " + " ".join(parts)) if parts else ""
    _logger.info("%s tenant=%s user=%s%s", event, ctx.tenant, ctx.user_id, tail)


def log_upsert(ctx: Ctx, model: str, records: list[dict[str, Any]]) -> None:
    bits: list[str] = []
    for rec in records[:_MAX_ITEMS]:
        changes = rec.get("changes") if isinstance(rec.get("changes"), dict) else {}
        names = [str(key) for key in changes if "password" not in str(key).lower()]
        shown = ",".join(names[:_MAX_FIELDS])
        if len(names) > _MAX_FIELDS:
            shown += f"+{len(names) - _MAX_FIELDS}"
        state = shown if rec.get("changed") else "unchanged"
        bits.append(f"{rec.get('opType')} {rec.get('uukey')} {state}")
    extra = f" +{len(records) - _MAX_ITEMS}" if len(records) > _MAX_ITEMS else ""
    log(ctx, "upsert", model=model, n=len(records), rows="; ".join(bits) + extra)


def log_delete(ctx: Ctx, model: str, keys: list[Any]) -> None:
    shown = ",".join(str(key) for key in keys[:_MAX_ITEMS])
    if len(keys) > _MAX_ITEMS:
        shown += f"+{len(keys) - _MAX_ITEMS}"
    log(ctx, "delete", model=model, n=len(keys), keys=shown)


def _fmt(val: Any) -> str:
    if val is None or val is False:
        return ""
    if isinstance(val, (list, tuple, set)):
        text = ",".join(str(item) for item in val if str(item or "").strip())
    else:
        text = str(val).replace("\n", " ").strip()
    if len(text) > 240:
        return text[:240] + "…"
    return text
