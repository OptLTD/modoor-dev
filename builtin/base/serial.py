"""Tenant-scoped business serial counters (`base_serial`).

SERIALNO allocation: PREFIX[+date] + zero-padded sequence, keyed by
(tenant, model, head). First use can seed ``value`` from an existing
business table's max uukey so legacy rows stay contiguous.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.db import Base


class BaseSerial(Base):
    """Per-tenant serial counter for a model + number head (prefix[+date])."""

    __tablename__ = "base_serial"
    __table_args__ = (
        UniqueConstraint("tenant", "model", "head", name="uq_base_serial_tenant_model_head"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    head: Mapped[str] = mapped_column(String(64))
    value: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def serial_date_stamp(mode: str | None, when: datetime | None = None) -> str:
    """SERIALNO ``extra.datetime`` → date segment in the business number."""
    m = str(mode or "").strip().upper()
    if m in ("", "HIDDEN", "NONE", "FALSE"):
        return ""
    dt = when or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if m == "ONLYMONTH":
        return dt.strftime("%Y%m")
    if m == "ONLYDATE":
        return dt.strftime("%Y%m%d")
    if m in ("DATETIME", "FULL"):
        return dt.strftime("%Y%m%d%H%M%S")
    return ""


def _max_from_cls(session: Session, cls: type, tenant: int, head: str) -> int:
    if not hasattr(cls, "uukey"):
        return 0
    like = f"{head}%"
    rows = session.scalars(
        select(cls.uukey).where(cls.tenant == tenant, cls.uukey.like(like))
    ).all()
    max_n = 0
    for raw in rows:
        s = str(raw or "").strip().upper()
        if not s.startswith(head):
            continue
        tail = s[len(head) :]
        if tail.isdigit():
            max_n = max(max_n, int(tail))
    return max_n


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def reserve_serials(
    session: Session,
    *,
    tenant: int,
    model: str,
    prefix: str,
    width: int = 5,
    datetime_mode: str | None = None,
    when: datetime | None = None,
    count: int = 1,
    seed_cls: type | None = None,
) -> list[str]:
    """Atomically reserve ``count`` consecutive serials; return formatted codes."""
    n = max(0, int(count or 0))
    if n <= 0:
        return []
    p = (prefix or "X").strip().upper() or "X"
    w = max(1, int(width or 5))
    mid = str(model or "").strip() or "_"
    head = f"{p}{serial_date_stamp(datetime_mode, when)}"

    for _ in range(5):
        row = session.scalar(
            select(BaseSerial)
            .where(
                BaseSerial.tenant == tenant,
                BaseSerial.model == mid,
                BaseSerial.head == head,
            )
            .with_for_update()
        )
        if row is None:
            seed = _max_from_cls(session, seed_cls, tenant, head) if seed_cls is not None else 0
            try:
                with session.begin_nested():
                    session.add(
                        BaseSerial(
                            id=str(uuid.uuid4()),
                            tenant=tenant,
                            model=mid,
                            head=head,
                            value=int(seed),
                            updated_at=_utcnow(),
                        )
                    )
                    session.flush()
            except IntegrityError:
                continue
            row = session.scalar(
                select(BaseSerial)
                .where(
                    BaseSerial.tenant == tenant,
                    BaseSerial.model == mid,
                    BaseSerial.head == head,
                )
                .with_for_update()
            )
            if row is None:
                continue

        start = int(row.value) + 1
        row.value = int(row.value) + n
        row.updated_at = _utcnow()
        session.flush()
        return [f"{head}{start + i:0{w}d}" for i in range(n)]

    raise RuntimeError(f"base_serial allocate failed: tenant={tenant} model={mid} head={head}")


def ensure_serial_at_least(
    session: Session,
    *,
    tenant: int,
    model: str,
    head: str,
    value: int,
) -> None:
    """Bump counter so ``value`` is covered (e.g. after in-memory seed)."""
    mid = str(model or "").strip() or "_"
    h = str(head or "").strip().upper()
    v = max(0, int(value or 0))
    if not h:
        return
    row = session.scalar(
        select(BaseSerial)
        .where(
            BaseSerial.tenant == tenant,
            BaseSerial.model == mid,
            BaseSerial.head == h,
        )
        .with_for_update()
    )
    if row is None:
        try:
            with session.begin_nested():
                session.add(
                    BaseSerial(
                        id=str(uuid.uuid4()),
                        tenant=tenant,
                        model=mid,
                        head=h,
                        value=v,
                        updated_at=_utcnow(),
                    )
                )
                session.flush()
            return
        except IntegrityError:
            row = session.scalar(
                select(BaseSerial)
                .where(
                    BaseSerial.tenant == tenant,
                    BaseSerial.model == mid,
                    BaseSerial.head == h,
                )
                .with_for_update()
            )
    if row is not None and int(row.value) < v:
        row.value = v
        row.updated_at = _utcnow()
        session.flush()


def delete_serials_for_models(session: Session, tenant: int, models: list[str] | tuple[str, ...]) -> int:
    """Drop counter rows for the given models (used by force seed wipe)."""
    mids = [str(m).strip() for m in models if str(m).strip()]
    if not mids:
        return 0
    rows = session.scalars(
        select(BaseSerial).where(BaseSerial.tenant == tenant, BaseSerial.model.in_(mids))
    ).all()
    n = 0
    for row in rows:
        session.delete(row)
        n += 1
    if n:
        session.flush()
    return n


def alloc_serial(
    session: Session,
    *,
    tenant: int,
    model: str,
    prefix: str,
    width: int = 5,
    datetime_mode: str | None = None,
    when: datetime | None = None,
    seed_cls: type | None = None,
) -> str:
    """Allocate one serial (convenience wrapper)."""
    return reserve_serials(
        session,
        tenant=tenant,
        model=model,
        prefix=prefix,
        width=width,
        datetime_mode=datetime_mode,
        when=when,
        count=1,
        seed_cls=seed_cls,
    )[0]
