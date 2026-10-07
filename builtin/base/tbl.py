"""List column settings (`base_tbl`).

One row is the column order and hidden fields for a model view.
``level`` is ``global`` for now; personal rows are not written yet.
``using`` is the tables.json view key (default, unsigned, signed).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import quoted_name

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError

TBL_LEVEL_GLOBAL = "global"


class BaseTbl(Base):
    """Tenant-wide column layout for one model view."""

    __tablename__ = "base_tbl"
    __table_args__ = (
        UniqueConstraint(
            "tenant",
            "model",
            "using",
            "level",
            name="uq_base_tbl_tenant_model_using_level",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    using: Mapped[str] = mapped_column(quoted_name("using", True), String(64), default="default")
    level: Mapped[str] = mapped_column(String(16), default=TBL_LEVEL_GLOBAL)
    data: Mapped[Any] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def _keys(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def normalize_tbl_data(raw: Any) -> dict[str, list[str]] | None:
    """``{ order, hidden }``. Empty means the view should fall back to tables.json."""
    if not isinstance(raw, dict):
        return None
    order = _keys(raw.get("order"))
    hidden = _keys(raw.get("hidden"))
    if not order and not hidden:
        return None
    return {"order": order, "hidden": hidden}


def _view(using: str | None) -> str:
    return str(using or "").strip() or "default"


def _model(model: str | None) -> str:
    m = str(model or "").strip()
    if not m:
        raise AppError("validation_error", "model required")
    return m


def get_table_setting(
    session: Session,
    ctx: Ctx,
    *,
    model: str,
    using: str | None = None,
) -> dict[str, Any] | None:
    m = _model(model)
    u = _view(using)
    row = session.scalar(
        select(BaseTbl)
        .where(
            BaseTbl.tenant == ctx.tenant,
            BaseTbl.model == m,
            BaseTbl.using == u,
            BaseTbl.level == TBL_LEVEL_GLOBAL,
        )
        .limit(1)
    )
    if row is None:
        return None
    data = normalize_tbl_data(row.data)
    if data is None:
        return None
    return {
        "model": row.model,
        "using": row.using,
        "level": row.level,
        "data": data,
    }


def upsert_table_setting(
    session: Session,
    ctx: Ctx,
    *,
    model: str,
    using: str | None = None,
    data: Any = None,
) -> dict[str, Any] | None:
    """Save global column settings. Empty data deletes the row."""
    m = _model(model)
    u = _view(using)
    payload = normalize_tbl_data(data)
    row = session.scalar(
        select(BaseTbl)
        .where(
            BaseTbl.tenant == ctx.tenant,
            BaseTbl.model == m,
            BaseTbl.using == u,
            BaseTbl.level == TBL_LEVEL_GLOBAL,
        )
        .limit(1)
    )
    if payload is None:
        if row is not None:
            session.delete(row)
            session.flush()
        return None
    now = datetime.now(timezone.utc)
    if row is None:
        row = BaseTbl(
            id=str(uuid.uuid4()),
            tenant=ctx.tenant,
            model=m,
            using=u,
            level=TBL_LEVEL_GLOBAL,
            data=payload,
            updated_at=now,
        )
        session.add(row)
    else:
        row.data = payload
        row.updated_at = now
    session.flush()
    return {
        "model": row.model,
        "using": row.using,
        "level": row.level,
        "data": payload,
    }
