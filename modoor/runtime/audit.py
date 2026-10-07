from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from modoor.core.ctx import Ctx
from modoor.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(256), index=True)
    args_summary: Mapped[str] = mapped_column(Text)
    result_status: Mapped[str] = mapped_column(String(64))


def write_audit(
    session: Session,
    *,
    ctx: Ctx,
    tool: str,
    args: dict[str, Any],
    result_status: str,
) -> None:
    redacted = {k: ("***" if k == "confirmation_token" else v) for k, v in args.items()}
    summary = json.dumps(redacted, ensure_ascii=False, default=str)[:2000]
    session.add(
        AuditLog(
            tenant=ctx.tenant,
            user_id=ctx.user_id,
            team_id=ctx.team_id,
            tool=tool,
            args_summary=summary,
            result_status=result_status,
        )
    )
