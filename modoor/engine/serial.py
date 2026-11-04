"""Tenant-scoped business serial counters (`base_serial`).

SERIALNO allocation: PREFIX[+date] + zero-padded sequence, keyed by
(tenant, model, head). First use can seed ``value`` from an existing
business table's max uukey so legacy rows stay contiguous.
"""

from __future__ import annotations

import re
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


def serial_spec(
    model: str,
    *,
    default_prefix: str = "X",
    default_width: int = 5,
    default_datetime: str = "HIDDEN",
) -> tuple[str, int, str]:
    """Read SERIALNO config ``(prefix, width, datetime mode)`` for a model.

    Values come from the ``basic.uukey`` / ``basic.code`` field's ``extra``
    (``constant`` / ``counting`` / ``datetime``), then the model's ``extra``.
    Falls back to the supplied defaults when the bundle or keys are missing.
    """
    prefix = str(default_prefix or "X").strip().upper() or "X"
    width = int(default_width or 5)
    datetime_mode = str(default_datetime or "HIDDEN").strip().upper() or "HIDDEN"
    try:
        from modoor.engine.registry import get_bundle

        bundle = get_bundle(model)
    except KeyError:
        return prefix, width, datetime_mode
    field = bundle.fields.get("basic.uukey") or bundle.fields.get("basic.code") or {}
    extra = dict(field.get("extra") or {})
    model_extra = dict(bundle.model.get("extra") or {})
    raw_prefix = extra.get("constant") or model_extra.get("constant")
    if str(raw_prefix or "").strip():
        prefix = str(raw_prefix).strip().upper()
    raw_width = extra.get("counting")
    if raw_width is None:
        raw_width = model_extra.get("counting")
    if raw_width is not None:
        try:
            parsed = int(raw_width)
        except (TypeError, ValueError):
            parsed = 0
        if parsed > 0:
            width = parsed
    raw_mode = extra.get("datetime") or model_extra.get("datetime")
    if str(raw_mode or "").strip():
        datetime_mode = str(raw_mode).strip().upper()
    return prefix, width, datetime_mode


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


def _lock_serial_row(
    session: Session,
    *,
    tenant: int,
    model: str,
    head: str,
    seed_cls: type | None = None,
) -> BaseSerial | None:
    row = session.scalar(
        select(BaseSerial)
        .where(
            BaseSerial.tenant == tenant,
            BaseSerial.model == model,
            BaseSerial.head == head,
        )
        .with_for_update()
    )
    if row is not None:
        return row
    seed = _max_from_cls(session, seed_cls, tenant, head) if seed_cls is not None else 0
    try:
        with session.begin_nested():
            session.add(
                BaseSerial(
                    id=str(uuid.uuid4()),
                    tenant=tenant,
                    model=model,
                    head=head,
                    value=int(seed),
                    updated_at=_utcnow(),
                )
            )
            session.flush()
    except IntegrityError:
        pass
    return session.scalar(
        select(BaseSerial)
        .where(
            BaseSerial.tenant == tenant,
            BaseSerial.model == model,
            BaseSerial.head == head,
        )
        .with_for_update()
    )


def preview_serials(
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
    """Pre-generate codes without advancing base_serial.

    Saving the record with one of these codes advances the counter in the same
    transaction. A failed save rolls back, so the code is not consumed.
    """
    n = max(0, int(count or 0))
    if n <= 0:
        return []
    p = (prefix or "X").strip().upper() or "X"
    w = max(1, int(width or 5))
    mid = str(model or "").strip() or "_"
    head = f"{p}{serial_date_stamp(datetime_mode, when)}"
    row = _lock_serial_row(session, tenant=tenant, model=mid, head=head, seed_cls=seed_cls)
    if row is None:
        raise RuntimeError(f"base_serial preview failed: tenant={tenant} model={mid} head={head}")
    if seed_cls is not None:
        # 只追平已有编号，不占用新号；防止手工/历史数据造成重复预览。
        max_used = _max_from_cls(session, seed_cls, tenant, head)
        if max_used > int(row.value):
            row.value = max_used
            row.updated_at = _utcnow()
            session.flush()
    start = int(row.value) + 1
    return [f"{head}{start + i:0{w}d}" for i in range(n)]


def _split_serial_code(
    session: Session,
    *,
    tenant: int,
    model: str,
    code: str,
    prefix: str | None = None,
    datetime_mode: str | None = None,
    width: int | None = None,
) -> tuple[str, int] | None:
    """Split a business code into ``(head, sequence)``.

    Heads may carry a date segment (``WB20261103``), so ``WB20261103001`` must
    not be split as head ``WB`` + sequence ``20261103001``. Prefer the longest
    head already stored for this model, then split structurally from the
    configured prefix + date segment, then fall back to the sequence width.
    """
    text = str(code or "").strip()
    if not text:
        return None
    known = session.scalars(
        select(BaseSerial.head).where(
            BaseSerial.tenant == tenant,
            BaseSerial.model == model,
        )
    ).all()
    best: tuple[str, int] | None = None
    for raw_head in known:
        head = str(raw_head or "")
        if not head or not text.startswith(head):
            continue
        tail = text[len(head) :]
        if not tail.isdigit():
            continue
        if best is None or len(head) > len(best[0]):
            best = (head, int(tail))
    if best is not None:
        return best
    p = str(prefix or "").strip()
    if p and text.startswith(p):
        stamp_len = len(serial_date_stamp(datetime_mode))
        cut = len(p) + stamp_len
        if len(text) > cut and text[cut:].isdigit():
            return text[:cut], int(text[cut:])
        if not stamp_len and len(text) > len(p) and text[len(p) :].isdigit():
            return p, int(text[len(p) :])
    w = int(width or 0)
    if w > 0 and len(text) > w and text[-w:].isdigit():
        return text[:-w], int(text[-w:])
    matched = re.match(r"^(.*?)(\d+)$", text)
    if not matched:
        return None
    return matched.group(1), int(matched.group(2))


def claim_serial(
    session: Session,
    *,
    tenant: int,
    model: str,
    code: str,
    prefix: str | None = None,
    datetime_mode: str | None = None,
    width: int | None = None,
) -> bool:
    """Advance the counter to a successfully saved explicit code."""
    mid = str(model or "").strip() or "_"
    split = _split_serial_code(
        session,
        tenant=tenant,
        model=mid,
        code=code,
        prefix=prefix,
        datetime_mode=datetime_mode,
        width=width,
    )
    if split is None:
        return False
    head, serial = split
    row = _lock_serial_row(session, tenant=tenant, model=mid, head=head)
    if row is None:
        return False
    if serial > int(row.value):
        row.value = serial
        row.updated_at = _utcnow()
    session.flush()
    return True


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
