"""Company-wide shell settings (base_cfg mod=base, type=global.settings).

One row per tenant: language, timezone, time format, and the module opened after login.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from builtin.base import domain as base_domain

GLOBAL_MOD = "base"
GLOBAL_TYPE = "global.settings"
MENU_LAYOUT = "menu.layout"

LOCALES = ("zh-CN", "en-US")
TIMEZONES: tuple[tuple[str, str, str], ...] = (
    ("Asia/Shanghai", "中国标准时间", "China Standard Time"),
    ("Asia/Hong_Kong", "香港", "Hong Kong"),
    ("Asia/Tokyo", "日本标准时间", "Japan Standard Time"),
    ("Asia/Singapore", "新加坡", "Singapore"),
    ("UTC", "UTC", "UTC"),
    ("Europe/London", "伦敦", "London"),
    ("America/New_York", "美国东部", "US Eastern"),
    ("America/Los_Angeles", "美国太平洋", "US Pacific"),
)
TIME_FORMATS = (
    "YYYY-MM-DD HH:mm:ss",
    "YYYY-MM-DD HH:mm",
    "YYYY/MM/DD HH:mm:ss",
    "DD/MM/YYYY HH:mm",
)
_MODULE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def default_global_settings() -> dict[str, str]:
    return {
        "locale": "zh-CN",
        "timezone": "Asia/Shanghai",
        "timeFormat": "YYYY-MM-DD HH:mm:ss",
        "defaultModule": "",
    }


def normalize_global_settings(raw: Any) -> dict[str, str]:
    out = default_global_settings()
    if not isinstance(raw, dict):
        return out
    locale = str(raw.get("locale") or "").strip().lower().replace("_", "-")
    if locale == "en" or locale.startswith("en-") or locale == "us-en":
        out["locale"] = "en-US"
    elif locale == "zh" or locale.startswith("zh-"):
        out["locale"] = "zh-CN"
    tz = str(raw.get("timezone") or "").strip()
    if tz in {item[0] for item in TIMEZONES}:
        out["timezone"] = tz
    fmt = str(raw.get("timeFormat") or "").strip()
    if fmt in TIME_FORMATS:
        out["timeFormat"] = fmt
    mid = str(raw.get("defaultModule") or "").strip()
    if mid and _MODULE_RE.match(mid):
        out["defaultModule"] = mid
    return out


def get_global_settings(session: Session, ctx: Ctx) -> dict[str, str]:
    row = base_domain.get_config(session, ctx, mod=GLOBAL_MOD, type=GLOBAL_TYPE)
    data = row.data if row is not None else None
    return normalize_global_settings(data)


def save_global_settings(
    session: Session,
    ctx: Ctx,
    raw: Any,
    *,
    enabled: set[str],
) -> dict[str, str]:
    data = normalize_global_settings(raw)
    mid = data["defaultModule"]
    if mid and mid not in enabled:
        raise AppError("validation_error", "default module is not enabled")
    base_domain.upsert_config(
        session,
        ctx,
        mod=GLOBAL_MOD,
        type=GLOBAL_TYPE,
        data=data,
        title="全局设置",
    )
    return data


def user_can_edit_global(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int,
    active_role: str | None = None,
) -> bool:
    access = base_domain.list_user_abilities(
        session, ctx, user_id=user_id, active_role=active_role
    )
    if access.get("unrestricted"):
        return True
    abilities = set(access.get("abilities") or [])
    return "base.app.write" in abilities or "base.user.write" in abilities


def normalize_menu_layouts(raw: Any) -> dict[str, str]:
    """Per-module nav position. Only ``side`` is stored; missing means top."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        mid = str(key or "").strip()
        if not mid or not _MODULE_RE.match(mid):
            continue
        if str(value or "").strip() == "side":
            out[mid] = "side"
    return out


def get_menu_layouts(session: Session, ctx: Ctx) -> dict[str, str]:
    row = base_domain.get_config(session, ctx, mod=GLOBAL_MOD, type=MENU_LAYOUT)
    data = row.data if row is not None else None
    return normalize_menu_layouts(data)


def save_module_menu_layout(
    session: Session,
    ctx: Ctx,
    module_id: str,
    layout: str,
) -> str:
    mid = str(module_id or "").strip()
    if not _MODULE_RE.match(mid):
        raise AppError("validation_error", "invalid module")
    choice = "side" if str(layout or "").strip() == "side" else "top"
    current = get_menu_layouts(session, ctx)
    if choice == "side":
        current[mid] = "side"
    else:
        current.pop(mid, None)
    base_domain.upsert_config(
        session, ctx,
        mod=GLOBAL_MOD,
        type=MENU_LAYOUT,
        data=current,
        title="菜单样式",
    )
    return choice


def landing_module(
    settings: dict[str, str],
    *,
    enabled: set[str],
    allowed: set[str] | None,
) -> str | None:
    """Module to open after login. Empty when the company stays on the workbench."""
    mid = str(settings.get("defaultModule") or "").strip()
    if not mid or mid not in enabled:
        return None
    if allowed is not None and mid not in allowed:
        return None
    return mid
