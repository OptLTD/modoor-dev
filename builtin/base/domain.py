"""Base module: App / User / Role / Team (tenant-scoped RBAC)."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, selectinload

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError
from modoor.engine.oplog import diff_row_values
from modoor.core.security import hash_password, verify_password
from modoor.core.state import STATE_ON, as_on, is_on

_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class SystemTenant(Base):
    __tablename__ = "base_tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SystemLogin(Base):
    """Global sign-in identity (not a business record; one login → many tenant users)."""

    __tablename__ = "base_login"
    __table_args__ = (
        UniqueConstraint("username", name="uq_base_login_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), index=True)
    password: Mapped[str | None] = mapped_column(String(256), nullable=True)
    realname: Mapped[str] = mapped_column(String(256), default="")
    current: Mapped[int | None] = mapped_column(
        ForeignKey("base_tenant.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    users: Mapped[list["SystemUser"]] = relationship(
        back_populates="login",
        primaryjoin="SystemUser.base_id==SystemLogin.id",
        foreign_keys="SystemUser.base_id",
    )


class SystemTeam(Base):
    """Tenant-scoped team / org-unit tree (team ≡ org)."""

    __tablename__ = "base_team"
    __table_args__ = (
        UniqueConstraint("tenant", "code", name="uq_base_team_tenant_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    utime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    name: Mapped[str] = mapped_column(String(256))
    seqno: Mapped[int] = mapped_column(Integer, default=0)
    # Soft-delete: STATE_ON alive, STATE_OFF deleted
    state: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    # Business enable/disable (启停); independent of soft-delete ``state``
    enable: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    parent: Mapped[int] = mapped_column(Integer, index=True, default=0)
    contact: Mapped[str | None] = mapped_column(String(256), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def active(self) -> bool:
        """Business enabled (启停); not soft-delete."""
        return is_on(self.enable)

    @property
    def uukey(self) -> str:
        """Sheet/record key alias for ``code``."""
        return self.code


class SystemUser(Base):
    __tablename__ = "base_user"
    __table_args__ = (
        UniqueConstraint("tenant", "code", name="uq_base_user_tenant_code"),
        UniqueConstraint("tenant", "base_id", name="uq_base_user_tenant_base"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    utime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    name: Mapped[str] = mapped_column(String(256), default="")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Soft-delete: STATE_ON alive, STATE_OFF deleted
    state: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    # Business enable/disable (启停); independent of soft-delete ``state``
    enable: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    base_id: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    # 登录身份：一份账号指向一份业务档案（模型 + 档案编号）。
    model: Mapped[str] = mapped_column(String(64), default="")
    refer: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    login: Mapped[SystemLogin] = relationship(
        back_populates="users",
        primaryjoin="SystemUser.base_id==SystemLogin.id",
        foreign_keys="SystemUser.base_id",
    )

    @property
    def username(self) -> str:
        return self.login.username if self.login is not None else ""

    @property
    def realname(self) -> str:
        return self.login.realname if self.login is not None else ""

    @property
    def display_name(self) -> str:
        return (self.name or self.realname or self.username or "").strip() or "—"

    @property
    def current(self) -> int | None:
        return self.login.current if self.login is not None else None

    @property
    def active(self) -> bool:
        """Usable in this tenant: alive (not soft-deleted) and enabled."""
        return is_on(self.state) and is_on(self.enable)

    @property
    def uukey(self) -> str:
        """Sheet/record key alias for ``code``."""
        return self.code


TOKEN_KIND_AGENT = "agent"
TOKEN_KIND_API = "api"


class SystemToken(Base):
    """Tenant-user credentials: agent MCP key, API key, etc."""

    __tablename__ = "base_token"
    __table_args__ = (
        UniqueConstraint("tenant", "kind", "token", name="uq_base_token_tenant_kind_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    token: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    # Kind-specific options, e.g. agent: {"readonly": true}
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def active(self) -> bool:
        return is_on(self.state)

    def extra_dict(self) -> dict[str, Any]:
        raw = self.extra
        return dict(raw) if isinstance(raw, dict) else {}

    def is_readonly(self) -> bool:
        """Agent tokens default readonly=True when unset."""
        extra = self.extra_dict()
        if "readonly" not in extra:
            return self.kind == TOKEN_KIND_AGENT
        return bool(extra.get("readonly"))

    def set_readonly(self, readonly: bool) -> None:
        extra = self.extra_dict()
        extra["readonly"] = bool(readonly)
        self.extra = extra


class SystemRole(Base):
    __tablename__ = "base_role"
    __table_args__ = (
        UniqueConstraint("tenant", "code", name="uq_base_role_tenant_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256))
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON: assigned user ids; ability/node codes
    users: Mapped[list] = mapped_column(JSON, default=list)
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    # Soft-delete: STATE_ON alive, STATE_OFF deleted
    state: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    # Business enable/disable (启停); independent of soft-delete ``state``
    enable: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def active(self) -> bool:
        """Business enabled (启停); not soft-delete."""
        return is_on(self.enable)


class SystemOplog(Base):
    """System operation log (local audit + duolali ``biz_sys_oplogs``)."""

    __tablename__ = "base_oplog"
    __table_args__ = (
        Index("ix_base_oplog_tenant_code", "tenant", "code"),
        Index("ix_base_oplog_tenant_utime", "tenant", "utime"),
        Index("ix_base_oplog_tenant_model_code", "tenant", "model", "code"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    # Business model (duolali BizSysOpLog.model → modoor target, e.g. fleet.driver)
    model: Mapped[str] = mapped_column(String(64), default="", index=True)
    # Source subject / serial (duolali basic.uukey → code)
    code: Mapped[str] = mapped_column(String(64), default="")
    utime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    values: Mapped[Any] = mapped_column(JSON, nullable=True)
    state: Mapped[int] = mapped_column(SmallInteger, default=STATE_ON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


def record_oplog(
    session: Session,
    ctx: Ctx,
    *,
    code: str,
    action: str,
    model: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    diff: dict[str, dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> SystemOplog | None:
    """Append one ``base.oplog`` audit row (create/update/delete with model diff).

    Skipped when ``ctx.skip_oplog`` or when auditing ``base.oplog`` itself.
    UPDATE with empty diff is a no-op.
    """
    if getattr(ctx, "skip_oplog", False):
        return None
    if model == "base.oplog":
        return None
    changes = diff if diff is not None else diff_row_values(before, after)
    op = str(action or "").strip().upper() or "UPSERT"
    if op in ("UPDATE", "UPSERT") and not changes:
        return None
    model_key = str(model or "").strip()
    payload: dict[str, Any] = {
        "model": model_key,
        "actor": ctx.user_id,
        "team_id": ctx.team_id,
        "diff": changes,
    }
    if extra:
        payload.update(extra)
    row = SystemOplog(
        id=str(uuid.uuid4()),
        tenant=ctx.tenant,
        model=model_key,
        code=str(code or "").strip(),
        utime=_now(),
        action=op,
        values=payload,
        state=STATE_ON,
    )
    session.add(row)
    session.flush()
    return row


def list_record_oplogs(
    session: Session,
    ctx: Ctx,
    *,
    code: str,
    model: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List ``base.oplog`` rows for one business code (newest first).

    When ``model`` is set, filter by column ``model`` (and ``values.model`` fallback),
    accepting sync source/target aliases (e.g. ``base.driver`` ↔ ``fleet.driver``).
    Rows with empty model tag are kept when ``code`` matches.
    """
    key = str(code or "").strip()
    if not key:
        return []
    want_model = str(model or "").strip() or None
    aliases: set[str] | None = None
    if want_model:
        try:
            from addon.sync.domain.mapping import model_aliases

            aliases = model_aliases(want_model) or {want_model}
        except Exception:  # noqa: BLE001 — sync addon optional at import time
            aliases = {want_model}
    stmt = (
        select(SystemOplog)
        .where(
            SystemOplog.tenant == ctx.tenant,
            SystemOplog.code == key,
            SystemOplog.state == STATE_ON,
        )
        .order_by(
            SystemOplog.utime.desc().nulls_last(),
            SystemOplog.created_at.desc(),
        )
    )
    # Over-fetch a bit when filtering by model so untagged / alias rows still surface.
    fetch_n = max(1, min(int(limit or 200), 500))
    if want_model:
        fetch_n = min(500, fetch_n * 3)
    rows = session.scalars(stmt.limit(fetch_n)).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        vals = row.values if isinstance(row.values, dict) else {}
        tagged = str(row.model or "").strip() or str(vals.get("model") or "").strip()
        if want_model and tagged and aliases is not None and tagged not in aliases:
            continue
        if isinstance(vals, dict) and tagged and not vals.get("model"):
            vals = {**vals, "model": tagged}
        out.append(
            {
                "id": row.id,
                "model": tagged or None,
                "code": row.code,
                "utime": row.utime.isoformat() if row.utime else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "action": row.action,
                "values": vals,
            }
        )
        if len(out) >= max(1, min(int(limit or 200), 500)):
            break
    return out


def _register_oplog_writer() -> None:
    from modoor.engine import oplog as eng_oplog

    eng_oplog.set_oplog_writer(record_oplog)


_register_oplog_writer()


def _norm_code(code: str, *, field: str = "code") -> str:
    value = (code or "").strip().lower()
    if not _CODE_RE.match(value):
        raise AppError(
            "validation_error",
            f"{field} must match ^[a-z][a-z0-9_-]{{1,63}}$",
        )
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _touch(obj: Any) -> None:
    obj.updated_at = _now()


def _is_head_parent(parent: int | None) -> bool:
    return parent is None or int(parent) == 0


def _head_parent_clause():
    return or_(SystemTeam.parent.is_(None), SystemTeam.parent == 0)


def _serialno(model: str, *, default_prefix: str, default_width: int = 5) -> tuple[str, int]:
    from modoor.engine.registry import get_bundle

    try:
        bundle = get_bundle(model)
    except KeyError:
        return default_prefix, default_width
    field = bundle.fields.get("basic.code") or bundle.fields.get("basic.uukey") or {}
    extra = dict(field.get("extra") or {})
    model_extra = dict(bundle.model.get("extra") or {})
    prefix = str(extra.get("constant") or model_extra.get("constant") or default_prefix).strip()
    raw = extra.get("counting")
    if raw is None:
        raw = model_extra.get("counting", default_width)
    try:
        width = int(raw)
    except (TypeError, ValueError):
        width = default_width
    if width < 1:
        width = default_width
    return prefix or default_prefix, width


def _next_uukey(
    session: Session,
    model: type,
    *,
    prefix: str,
    width: int = 5,
    tenant: int | None = None,
    attr: str = "uukey",
) -> str:
    col = getattr(model, attr)
    stmt = select(col).where(col.like(f"{prefix}%"))
    if tenant is not None and hasattr(model, "tenant"):
        stmt = stmt.where(model.tenant == tenant)
    max_n = 0
    for key in session.scalars(stmt).all():
        if not key:
            continue
        tail = str(key)[len(prefix) :]
        if tail.isdigit():
            max_n = max(max_n, int(tail))
    return f"{prefix}{max_n + 1:0{width}d}"


def _get_login_by_username(session: Session, username: str) -> SystemLogin | None:
    return session.scalar(
        select(SystemLogin).where(SystemLogin.username == username.strip().lower())
    )


def _norm_account(value: str | None) -> str:
    return (value or "").strip().lower()


def _apply_login_profile(
    row: SystemLogin,
    *,
    realname: str | None = None,
    tenant: int | None = None,
    overwrite_name: bool = False,
) -> None:
    if realname is not None:
        name = realname.strip()
        if name and (overwrite_name or not (row.realname or "").strip()):
            row.realname = name
    if tenant is not None and row.current is None:
        row.current = tenant


def _ensure_login(
    session: Session,
    ctx: Ctx,
    *,
    username: str,
    password: str | None = None,
    realname: str | None = None,
    overwrite_name: bool = False,
    overwrite_password: bool = False,
) -> SystemLogin:
    username = username.strip().lower()
    if not username or " " in username:
        raise AppError("validation_error", "username is required and must not contain spaces")
    row = _get_login_by_username(session, username)
    if row is None:
        row = SystemLogin(
            username=username,
            password=hash_password(password) if password else None,
            realname=(realname or "").strip(),
            current=ctx.tenant,
        )
        session.add(row)
        session.flush()
        return row
    _apply_login_profile(
        row, realname=realname, tenant=ctx.tenant, overwrite_name=overwrite_name
    )
    if password and (overwrite_password or not row.password):
        row.password = hash_password(password)
    _touch(row)
    session.flush()
    return row


def _bind_login_for_user(
    session: Session,
    ctx: Ctx,
    *,
    username: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
    realname: str | None = None,
) -> SystemLogin:
    """Resolve login for an unbound employee: email/phone as username, reuse if present."""
    uname = _norm_account(username)
    mail = _norm_account(email)
    mobile = _norm_account(phone)
    if uname:
        return _ensure_login(
            session,
            ctx,
            username=uname,
            password=password,
            realname=realname,
            overwrite_name=True,
        )
    if not mail and not mobile:
        raise AppError("validation_error", "email or phone is required")
    for key in (mail, mobile):
        if not key:
            continue
        row = _get_login_by_username(session, key)
        if row is None:
            continue
        _apply_login_profile(
            row, realname=realname, tenant=ctx.tenant, overwrite_name=True
        )
        if password and not row.password:
            row.password = hash_password(password)
        _touch(row)
        session.flush()
        return row
    return _ensure_login(
        session,
        ctx,
        username=mail or mobile,
        password=password,
        realname=realname,
        overwrite_name=True,
    )


def _assert_unique_contacts(
    session: Session,
    tenant: int,
    *,
    email: str | None = None,
    phone: str | None = None,
    exclude_id: int | None = None,
) -> None:
    mail = (email or "").strip()
    mobile = (phone or "").strip()
    if mail:
        stmt = select(SystemUser.id).where(
            SystemUser.tenant == tenant,
            func.lower(func.btrim(SystemUser.email)) == mail.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(SystemUser.id != exclude_id)
        if session.scalar(stmt) is not None:
            raise AppError("conflict", f"email already exists: {mail}")
    if mobile:
        stmt = select(SystemUser.id).where(
            SystemUser.tenant == tenant,
            func.lower(func.btrim(SystemUser.phone)) == mobile.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(SystemUser.id != exclude_id)
        if session.scalar(stmt) is not None:
            raise AppError("conflict", f"phone already exists: {mobile}")


def _attach_login(session: Session, ctx: Ctx, row: SystemUser, login: SystemLogin) -> None:
    exists = session.scalar(
        select(SystemUser).where(
            SystemUser.tenant == ctx.tenant, SystemUser.base_id == login.id
        )
    )
    if exists is not None and exists.id != row.id:
        raise AppError("conflict", f"username already exists: {login.username}")
    row.base_id = login.id


def _user_dict(row: SystemUser) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "uukey": row.code,
        "utime": row.utime.isoformat() if row.utime else None,
        "state": row.state,
        "enable": int(row.enable or 0),
        "tenant": row.tenant,
        "team_id": row.team_id,
        "base_id": row.base_id,
        "username": row.username,
        "realname": row.realname,
        "current": row.current,
        "name": row.name,
        "phone": row.phone,
        "email": row.email,
        "remark": row.remark,
        "model": row.model or "",
        "refer": row.refer or "",
        "active": row.active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _team_dict(row: SystemTeam) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "uukey": row.code,
        "utime": row.utime.isoformat() if row.utime else None,
        "state": row.state,
        "enable": int(row.enable or 0),
        "name": row.name,
        "seqno": row.seqno,
        "tenant": row.tenant,
        "parent": row.parent,
        "contact": row.contact,
        "address": row.address,
        "remark": row.remark,
        "active": row.active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _role_users(row: SystemRole) -> list[int]:
    raw = row.users if isinstance(row.users, list) else []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _role_nodes(row: SystemRole) -> list[str]:
    raw = row.nodes if isinstance(row.nodes, list) else []
    return sorted({str(x).strip() for x in raw if str(x).strip()})


def _role_dict(row: SystemRole) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant": row.tenant,
        "team_id": row.team_id,
        "code": row.code,
        "uukey": row.code,
        "name": row.name,
        "desc": row.desc,
        "users": _role_users(row),
        "nodes": _role_nodes(row),
        "state": row.state,
        "enable": int(row.enable or 0),
        "active": row.active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _scoped(stmt, ctx: Ctx, model):
    return stmt.where(model.tenant == ctx.tenant)


def _tenant_dict(row: SystemTenant) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_tenant_by_name(session: Session, name: str) -> SystemTenant:
    name = (name or "").strip()
    if not name:
        raise AppError("validation_error", "tenant name is required")
    row = session.scalar(select(SystemTenant).where(SystemTenant.name == name))
    if row is None:
        raise AppError("not_found", f"Tenant not found: {name}")
    return row


def get_tenant(session: Session, tenant_id: int) -> SystemTenant:
    row = session.get(SystemTenant, tenant_id)
    if row is None:
        raise AppError("not_found", "Tenant not found")
    return row


def _sync_tenant_id_sequence(session: Session) -> None:
    """Keep Postgres serial in sync after inserting an explicit tenant id."""
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    session.execute(
        text(
            "SELECT setval("
            "pg_get_serial_sequence('base_tenant', 'id'), "
            "COALESCE((SELECT MAX(id) FROM base_tenant), 1))"
        )
    )


def ensure_tenant(
    session: Session,
    name: str,
    *,
    tenant_id: int | None = None,
    create_head_team: bool = True,
) -> dict[str, Any]:
    """Create tenant + same-named head team if missing. Idempotent.

    When ``tenant_id`` is set, look up / create by that id (name used on create).
    If the tenant already exists, head-team creation is skipped when
    ``create_head_team`` is False (bootstrap uses this to leave existing orgs alone).
    """
    name = (name or "").strip()
    if not name:
        raise AppError("validation_error", "tenant name is required")
    created_tenant = False
    created_team = False
    row: SystemTenant | None = None
    if tenant_id is not None:
        row = session.get(SystemTenant, tenant_id)
        if row is None:
            clash = session.scalar(select(SystemTenant).where(SystemTenant.name == name))
            if clash is not None:
                raise AppError(
                    "conflict",
                    f"Tenant name {name!r} already used by id={clash.id}",
                )
            row = SystemTenant(id=tenant_id, name=name)
            session.add(row)
            session.flush()
            _sync_tenant_id_sequence(session)
            created_tenant = True
    else:
        row = session.scalar(select(SystemTenant).where(SystemTenant.name == name))
        if row is None:
            row = SystemTenant(name=name)
            session.add(row)
            session.flush()
            created_tenant = True

    # Existing tenant: optionally skip ensuring head team (caller already has org).
    if not created_tenant and not create_head_team:
        root = session.scalar(
            select(SystemTeam)
            .where(SystemTeam.tenant == row.id, _head_parent_clause())
            .order_by(SystemTeam.seqno, SystemTeam.id)
        )
        return {
            "tenant": _tenant_dict(row),
            "team": _team_dict(root) if root is not None else None,
            "created_tenant": False,
            "created_team": False,
        }

    root = session.scalar(
        select(SystemTeam)
        .where(
            SystemTeam.tenant == row.id,
            _head_parent_clause(),
            SystemTeam.name == name,
        )
        .order_by(SystemTeam.seqno, SystemTeam.id)
    )
    if root is None:
        root = session.scalar(
            select(SystemTeam)
            .where(SystemTeam.tenant == row.id, _head_parent_clause())
            .order_by(SystemTeam.seqno, SystemTeam.id)
        )
    if root is None:
        root = SystemTeam(
            tenant=row.id,
            code=_next_uukey(session, SystemTeam, prefix="TM", width=5, tenant=row.id, attr="code"),
            utime=_now(),
            state=STATE_ON,
            enable=STATE_ON,
            parent=0,
            name=name,
            seqno=0,
            created_by=0,
        )
        session.add(root)
        session.flush()
        created_team = True
    return {
        "tenant": _tenant_dict(row),
        "team": _team_dict(root),
        "created_tenant": created_tenant,
        "created_team": created_team,
    }


def root_team_id(session: Session, tenant_id: int) -> int:
    root = session.scalar(
        select(SystemTeam)
        .where(SystemTeam.tenant == tenant_id, _head_parent_clause())
        .order_by(SystemTeam.seqno, SystemTeam.id)
    )
    if root is None:
        raise AppError("not_found", "Root team not found for tenant")
    return root.id


def _user_query(session: Session):
    return select(SystemUser).options(selectinload(SystemUser.login))


def _get_user(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int | None = None,
    username: str | None = None,
    uukey: str | None = None,
) -> SystemUser:
    row: SystemUser | None = None
    stmt = _user_query(session).where(SystemUser.tenant == ctx.tenant)
    if user_id is not None:
        row = session.scalar(stmt.where(SystemUser.id == user_id))
    elif uukey:
        row = session.scalar(stmt.where(SystemUser.code == uukey.strip()))
    elif username:
        row = session.scalar(
            stmt.join(SystemLogin, SystemUser.base_id == SystemLogin.id).where(
                SystemLogin.username == username.strip().lower()
            )
        )
    else:
        raise AppError("validation_error", "user_id, uukey or username is required")
    if row is None or row.tenant != ctx.tenant:
        raise AppError("not_found", "User not found")
    return row


def load_user(
    session: Session, user_id: int, *, tenant: int | None = None
) -> SystemUser | None:
    stmt = _user_query(session).where(SystemUser.id == user_id)
    if tenant is not None:
        stmt = stmt.where(SystemUser.tenant == tenant)
    return session.scalar(stmt)


def resolve_user_key(session: Session, ctx: Ctx, key: str | int) -> SystemUser:
    raw = str(key).strip()
    if raw.isdigit():
        return _get_user(session, ctx, user_id=int(raw))
    return _get_user(session, ctx, uukey=raw)


def _get_role(
    session: Session, ctx: Ctx, *, role_id: str | None = None, code: str | None = None
) -> SystemRole:
    if role_id:
        row = session.get(SystemRole, role_id)
    elif code:
        row = session.scalar(
            select(SystemRole).where(
                SystemRole.tenant == ctx.tenant,
                SystemRole.code == _norm_code(code),
            )
        )
    else:
        raise AppError("validation_error", "role_id or code is required")
    if row is None or row.tenant != ctx.tenant:
        raise AppError("not_found", "Role not found")
    return row


# ---- User ----

def create_user(
    session: Session,
    ctx: Ctx,
    *,
    username: str | None = None,
    realname: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    remark: str | None = None,
    password: str | None = None,
    team_id: int | None = None,
    name: str | None = None,
    utime: datetime | None = None,
    code: str | None = None,
    model: str | None = None,
    refer: str | None = None,
) -> dict[str, Any]:
    local_name = (name or realname or "").strip()
    if not local_name:
        raise AppError("validation_error", "name is required")
    login_realname = (realname or local_name).strip()
    prefix, width = _serialno("base.user", default_prefix="USER")
    biz = (code or "").strip()
    if not biz:
        biz = _next_uukey(
            session, SystemUser, prefix=prefix, width=width, tenant=ctx.tenant, attr="code"
        )
    else:
        clash = session.scalar(
            select(SystemUser).where(SystemUser.tenant == ctx.tenant, SystemUser.code == biz)
        )
        if clash is not None:
            raise AppError("conflict", f"user code already exists: {biz}")
    mail = (email.strip() if email else None) or None
    mobile = (phone.strip() if phone else None) or None
    _assert_unique_contacts(session, ctx.tenant, email=mail, phone=mobile)
    login = _bind_login_for_user(
        session,
        ctx,
        username=username,
        email=mail,
        phone=mobile,
        password=password,
        realname=login_realname,
    )
    exists = session.scalar(
        select(SystemUser).where(
            SystemUser.tenant == ctx.tenant, SystemUser.base_id == login.id
        )
    )
    if exists:
        raise AppError("conflict", f"username already exists: {login.username}")
    resolved_team = team_id if team_id is not None else ctx.team_id
    resolved_team = _get_team(session, ctx, team_id=resolved_team).id
    row = SystemUser(
        tenant=ctx.tenant,
        code=biz,
        utime=utime or _now(),
        state=STATE_ON,
        enable=STATE_ON,
        base_id=login.id,
        team_id=resolved_team,
        name=local_name,
        phone=(phone.strip() if phone else None),
        email=(email.strip() if email else None),
        remark=(remark.strip() if remark else None),
        model=(model or "").strip(),
        refer=(refer or "").strip(),
        created_by=ctx.user_id,
    )
    session.add(row)
    session.flush()
    session.refresh(row, attribute_names=["login"])
    return _user_dict(row)


def update_user(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int | None = None,
    username: str | None = None,
    uukey: str | None = None,
    realname: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    remark: str | None = None,
    email: str | None = None,
    active: bool | None = None,
    password: str | None = None,
    team_id: int | None = ...,  # type: ignore[assignment]
    utime: datetime | None = ...,  # type: ignore[assignment]
    model: str | None = ...,  # type: ignore[assignment]
    refer: str | None = ...,  # type: ignore[assignment]
) -> dict[str, Any]:
    row = _get_user(session, ctx, user_id=user_id, username=username, uukey=uukey)
    if (
        realname is None
        and name is None
        and phone is None
        and remark is None
        and email is None
        and active is None
        and password is None
        and team_id is ...
        and utime is ...
        and model is ...
        and refer is ...
    ):
        raise AppError(
            "validation_error",
            "provide realname, name, phone, remark, email, active, password, team_id, and/or utime",
        )
    if name is not None:
        row.name = name.strip()
    next_phone = phone.strip() or None if phone is not None else row.phone
    next_email = email.strip() or None if email is not None else row.email
    if email is not None or phone is not None:
        _assert_unique_contacts(
            session,
            ctx.tenant,
            email=next_email if email is not None else None,
            phone=next_phone if phone is not None else None,
            exclude_id=row.id,
        )
    if phone is not None:
        row.phone = next_phone
    if remark is not None:
        row.remark = remark.strip() or None
    if email is not None:
        row.email = next_email
    if active is not None:
        if active is False and row.id == ctx.user_id:
            raise AppError("validation_error", "cannot disable the current user")
        row.enable = as_on(active)
    login_realname = None
    if realname is not None:
        realname = realname.strip()
        if not realname:
            raise AppError("validation_error", "realname cannot be empty")
        login_realname = realname
    elif name is not None:
        login_realname = row.name or None
    if row.login is None:
        login = _bind_login_for_user(
            session,
            ctx,
            email=row.email,
            phone=row.phone,
            password=password,
            realname=login_realname or row.name,
        )
        _attach_login(session, ctx, row, login)
        session.flush()
        session.refresh(row, attribute_names=["login"])
    else:
        if login_realname:
            _apply_login_profile(row.login, realname=login_realname, overwrite_name=True)
            _touch(row.login)
        if password is not None:
            if not password:
                raise AppError("validation_error", "password cannot be empty")
            row.login.password = hash_password(password)
            _touch(row.login)
    if team_id is not ...:
        if team_id is None:
            raise AppError("validation_error", "team_id is required")
        row.team_id = _get_team(session, ctx, team_id=team_id).id
    if utime is not ...:
        if utime is None:
            raise AppError("validation_error", "utime is required")
        row.utime = utime
    if model is not ...:
        row.model = str(model or "").strip()
    if refer is not ...:
        row.refer = str(refer or "").strip()
    _touch(row)
    session.flush()
    return _user_dict(row)


def get_user(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int | None = None,
    username: str | None = None,
    uukey: str | None = None,
) -> dict[str, Any]:
    return _user_dict(_get_user(session, ctx, user_id=user_id, username=username, uukey=uukey))


def list_users(
    session: Session,
    ctx: Ctx,
    *,
    q: str | None = None,
    team_id: int | None = None,
    include_descendants: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        raise AppError("validation_error", "limit must be between 1 and 200")
    stmt = (
        _user_query(session)
        .where(SystemUser.tenant == ctx.tenant, SystemUser.state == STATE_ON)
        .join(SystemLogin, SystemUser.base_id == SystemLogin.id)
        .order_by(SystemLogin.username)
        .limit(limit)
    )
    if team_id is not None:
        if include_descendants:
            ids = _team_descendant_ids(session, ctx, team_id)
            stmt = stmt.where(SystemUser.team_id.in_(ids))
        else:
            _get_team(session, ctx, team_id=team_id)
            stmt = stmt.where(SystemUser.team_id == team_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (SystemLogin.username.ilike(like))
            | (SystemLogin.realname.ilike(like))
            | (SystemUser.name.ilike(like))
        )
    rows = list(session.scalars(stmt))
    return {"items": [_user_dict(r) for r in rows], "count": len(rows)}


def delete_user(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int | None = None,
    username: str | None = None,
    uukey: str | None = None,
) -> dict[str, Any]:
    row = _get_user(session, ctx, user_id=user_id, username=username, uukey=uukey)
    # Drop user id from all role.users JSON lists in tenant
    roles = list(session.scalars(select(SystemRole).where(SystemRole.tenant == ctx.tenant)))
    for role in roles:
        ids = _role_users(role)
        if row.id in ids:
            role.users = [i for i in ids if i != row.id]
            _touch(role)
    payload = _user_dict(row)
    row.state = STATE_OFF
    _touch(row)
    session.flush()
    return {"deleted": True, "user": _user_dict(row)}


# ---- Team (org unit) ----

def _get_team(session: Session, ctx: Ctx, *, team_id: int) -> SystemTeam:
    row = session.get(SystemTeam, team_id)
    if row is None or row.tenant != ctx.tenant:
        raise AppError("not_found", "Team not found")
    return row


def _team_descendant_ids(session: Session, ctx: Ctx, root_id: int) -> list[int]:
    _get_team(session, ctx, team_id=root_id)
    rows = list(
        session.scalars(select(SystemTeam).where(SystemTeam.tenant == ctx.tenant))
    )
    children: dict[int | None, list[int]] = {}
    for r in rows:
        children.setdefault(r.parent, []).append(r.id)
    out: list[int] = []
    stack = [root_id]
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out


def create_team(
    session: Session,
    ctx: Ctx,
    *,
    name: str,
    parent: int | None = None,
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise AppError("validation_error", "name is required")
    # Flat org: every team hangs directly under the head team.
    parent = root_team_id(session, ctx.tenant)
    siblings = list(
        session.scalars(
            select(SystemTeam).where(
                SystemTeam.tenant == ctx.tenant,
                SystemTeam.parent == parent,
            )
        )
    )
    row = SystemTeam(
        tenant=ctx.tenant,
        code=_next_uukey(session, SystemTeam, prefix="TM", width=5, tenant=ctx.tenant, attr="code"),
        utime=_now(),
        state=STATE_ON,
        enable=STATE_ON,
        parent=parent,
        name=name,
        seqno=len(siblings),
        created_by=ctx.user_id,
    )
    session.add(row)
    session.flush()
    return _team_dict(row)


def update_team(
    session: Session,
    ctx: Ctx,
    *,
    team_id: int,
    name: str | None = None,
    parent: int | None = ...,  # type: ignore[assignment]
    active: bool | None = None,
) -> dict[str, Any]:
    row = _get_team(session, ctx, team_id=team_id)
    if name is None and parent is ... and active is None:
        raise AppError("validation_error", "provide name, parent, and/or active")
    if name is not None:
        name = name.strip()
        if not name:
            raise AppError("validation_error", "name cannot be empty")
        row.name = name
    if parent is not ...:
        if _is_head_parent(row.parent):
            raise AppError("validation_error", "cannot reparent the head team")
        head = root_team_id(session, ctx.tenant)
        if parent is None or parent != head:
            raise AppError("validation_error", "teams must hang under the head team")
        if parent == row.id:
            raise AppError("validation_error", "team cannot be its own parent")
        row.parent = parent
    if active is not None:
        row.enable = as_on(active)
    _touch(row)
    session.flush()
    return _team_dict(row)


def delete_team(session: Session, ctx: Ctx, *, team_id: int) -> dict[str, Any]:
    row = _get_team(session, ctx, team_id=team_id)
    if _is_head_parent(row.parent):
        raise AppError("conflict", "cannot delete the root team")
    child = session.scalar(
        select(SystemTeam).where(SystemTeam.tenant == ctx.tenant, SystemTeam.parent == row.id)
    )
    if child:
        raise AppError("conflict", "team has children; move or delete them first")
    fallback = row.parent
    users = session.scalars(
        select(SystemUser).where(SystemUser.tenant == ctx.tenant, SystemUser.team_id == row.id)
    ).all()
    for u in users:
        u.team_id = fallback
        _touch(u)
    payload = _team_dict(row)
    row.state = STATE_OFF
    _touch(row)
    session.flush()
    return {"deleted": True, "team": _team_dict(row)}


def list_team_tree(session: Session, ctx: Ctx) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(SystemTeam)
            .where(SystemTeam.tenant == ctx.tenant, SystemTeam.state == STATE_ON)
            .order_by(SystemTeam.seqno, SystemTeam.name)
        )
    )
    # Head team uses parent=0 (or None); normalize so the tree root is visible.
    by_parent: dict[int | None, list[SystemTeam]] = {}
    for r in rows:
        key: int | None = None if _is_head_parent(r.parent) else int(r.parent)
        by_parent.setdefault(key, []).append(r)

    def build(pid: int | None) -> list[dict[str, Any]]:
        return [
            {**_team_dict(r), "children": build(r.id)}
            for r in by_parent.get(pid, [])
        ]

    tree = build(None)
    return {"tree": tree, "count": len(rows)}


def list_team_options(session: Session, ctx: Ctx) -> list[dict[str, str]]:
    rows = list(
        session.scalars(
            select(SystemTeam)
            .where(SystemTeam.tenant == ctx.tenant, SystemTeam.state == STATE_ON)
            .order_by(SystemTeam.seqno, SystemTeam.id)
        )
    )
    rows.sort(key=lambda r: (r.parent is not None, r.seqno, r.id))
    return [{"uukey": str(r.id), "label": r.name} for r in rows]


# ---- Role ----

def create_role(
    session: Session,
    ctx: Ctx,
    *,
    name: str,
    code: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise AppError("validation_error", "name is required")
    if code:
        code = _norm_code(code)
    else:
        prefix, width = _serialno("base.role", default_prefix="role")
        prefix = prefix.strip().lower() or "role"
        code = _next_uukey(
            session,
            SystemRole,
            prefix=prefix,
            width=width,
            tenant=ctx.tenant,
            attr="code",
        )
    if session.scalar(
        select(SystemRole).where(
            SystemRole.tenant == ctx.tenant,
            SystemRole.code == code,
        )
    ):
        raise AppError("conflict", f"role code already exists: {code}")
    row = SystemRole(
        id=str(uuid.uuid4()),
        tenant=ctx.tenant,
        team_id=ctx.team_id,
        code=code,
        name=name,
        desc=description,
        users=[],
        nodes=[],
        state=STATE_ON,
        enable=STATE_ON,
        created_by=ctx.user_id,
    )
    session.add(row)
    session.flush()
    return _role_dict(row)


def update_role(
    session: Session,
    ctx: Ctx,
    *,
    role_id: str | None = None,
    code: str | None = None,
    name: str | None = None,
    description: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    row = _get_role(session, ctx, role_id=role_id, code=code)
    if name is None and description is None and active is None:
        raise AppError("validation_error", "provide name, description, and/or active")
    if name is not None:
        name = name.strip()
        if not name:
            raise AppError("validation_error", "name cannot be empty")
        row.name = name
    if description is not None:
        row.desc = description
    if active is not None:
        row.enable = as_on(active)
    _touch(row)
    session.flush()
    return _role_dict(row)


def get_role(
    session: Session,
    ctx: Ctx,
    *,
    role_id: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    return _role_dict(_get_role(session, ctx, role_id=role_id, code=code))


def list_roles(
    session: Session,
    ctx: Ctx,
    *,
    q: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        raise AppError("validation_error", "limit must be between 1 and 200")
    stmt = (
        _scoped(select(SystemRole), ctx, SystemRole)
        .where(SystemRole.state == STATE_ON)
        .order_by(SystemRole.code)
        .limit(limit)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((SystemRole.code.ilike(like)) | (SystemRole.name.ilike(like)))
    rows = list(session.scalars(stmt))
    return {"items": [_role_dict(r) for r in rows], "count": len(rows)}


def delete_role(
    session: Session,
    ctx: Ctx,
    *,
    role_id: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    row = _get_role(session, ctx, role_id=role_id, code=code)
    payload = _role_dict(row)
    row.state = STATE_OFF
    _touch(row)
    session.flush()
    return {"deleted": True, "role": _role_dict(row)}


# ---- Assignment (JSON on role.users) ----

def assign_role(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int,
    role_id: str,
) -> dict[str, Any]:
    user = _get_user(session, ctx, user_id=user_id)
    role = _get_role(session, ctx, role_id=role_id)
    ids = _role_users(role)
    if user.id in ids:
        raise AppError("conflict", "role already assigned to user")
    role.users = [*ids, user.id]
    _touch(role)
    session.flush()
    return {
        "user_id": user.id,
        "role_id": role.id,
        "users": _role_users(role),
        "assigned_by": ctx.user_id,
    }


def revoke_role(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int,
    role_id: str,
) -> dict[str, Any]:
    user = _get_user(session, ctx, user_id=user_id)
    role = _get_role(session, ctx, role_id=role_id)
    ids = _role_users(role)
    if user.id not in ids:
        raise AppError("not_found", "role assignment not found")
    role.users = [i for i in ids if i != user.id]
    _touch(role)
    session.flush()
    return {"revoked": True, "user_id": user.id, "role_id": role.id}


def list_user_roles(session: Session, ctx: Ctx, *, user_id: int) -> dict[str, Any]:
    user = _get_user(session, ctx, user_id=user_id)
    roles_rows = list(
        session.scalars(select(SystemRole).where(SystemRole.tenant == ctx.tenant))
    )
    roles = [_role_dict(r) for r in roles_rows if user.id in _role_users(r)]
    return {"user_id": user.id, "roles": roles, "count": len(roles)}


def list_user_abilities(
    session: Session, ctx: Ctx, *, user_id: int
) -> dict[str, Any]:
    """Effective abilities for a user = union of held role.nodes.

    Role code ``admin`` is unrestricted (sees all enabled modules) even when nodes are empty.
    """
    roles = list_user_roles(session, ctx, user_id=user_id)["roles"]
    if any(str(r.get("code") or "") == "admin" for r in roles):
        return {
            "user_id": user_id,
            "unrestricted": True,
            "abilities": [],
            "roles": [r["code"] for r in roles],
        }
    abilities: set[str] = set()
    for role in roles:
        for node in role.get("nodes") or []:
            code = str(node).strip()
            if code:
                abilities.add(code)
    return {
        "user_id": user_id,
        "unrestricted": False,
        "abilities": sorted(abilities),
        "roles": [r["code"] for r in roles],
    }


def module_allowed_by_abilities(module_id: str, abilities: set[str] | list[str]) -> bool:
    mid = str(module_id or "").strip()
    if not mid:
        return False
    prefix = f"{mid}."
    for raw in abilities:
        code = str(raw).strip()
        if not code:
            continue
        if code == mid or code.startswith(prefix):
            return True
    return False


def allowed_modules_for_user(
    session: Session,
    ctx: Ctx,
    *,
    user_id: int,
    enabled: set[str],
    extra_module_ids: set[str] | None = None,
) -> set[str] | None:
    """Return module ids visible in the shell, or None when unrestricted (no filter)."""
    access = list_user_abilities(session, ctx, user_id=user_id)
    if access["unrestricted"]:
        return None
    abilities = set(access["abilities"])
    candidates = set(enabled) | {"base"}
    if extra_module_ids:
        candidates |= set(extra_module_ids)
    return {mid for mid in candidates if module_allowed_by_abilities(mid, abilities)}


def list_ability_catalog(settings: Any | None = None) -> dict[str, Any]:
    """Aggregate ability codes from all module manifests, grouped by module."""
    from modoor.platform.module_state import discover_manifests

    modules: list[dict[str, Any]] = []
    for m in discover_manifests(settings):
        abilities = [str(a) for a in (m.get("ability") or []) if str(a).strip()]
        if not abilities:
            continue
        modules.append(
            {
                "module_id": m["id"],
                "label": m.get("label") or m["id"],
                "i18n": m.get("i18n") or {},
                "abilities": abilities,
            }
        )
    flat = sorted({a for g in modules for a in g["abilities"]})
    return {"modules": modules, "abilities": flat, "count": len(flat)}


def list_role_nodes(session: Session, ctx: Ctx, *, role_id: str) -> dict[str, Any]:
    role = _get_role(session, ctx, role_id=role_id)
    nodes = _role_nodes(role)
    return {"role_id": role.id, "nodes": nodes, "count": len(nodes)}


def set_role_nodes(
    session: Session,
    ctx: Ctx,
    *,
    role_id: str,
    nodes: list[str],
) -> dict[str, Any]:
    role = _get_role(session, ctx, role_id=role_id)
    wanted = sorted({str(a).strip() for a in nodes if str(a).strip()})
    role.nodes = wanted
    _touch(role)
    session.flush()
    return list_role_nodes(session, ctx, role_id=role.id)


def authenticate_user(
    session: Session,
    *,
    username: str,
    password: str,
    tenant: int | None = None,
    allow_fallback: bool = False,
) -> SystemUser:
    username = username.strip().lower()
    login = _get_login_by_username(session, username)
    if login is None:
        raise AppError("permission_denied", "Invalid username or password")
    if not login.password or not verify_password(password, login.password):
        raise AppError("permission_denied", "Invalid username or password")
    users = list(
        session.scalars(
            _user_query(session)
            .where(SystemUser.base_id == login.id)
            .order_by(SystemUser.id)
        )
    )
    users = [u for u in users if u.active]
    if not users:
        raise AppError("permission_denied", "Invalid username or password")

    chosen: SystemUser | None = None
    if tenant is not None:
        chosen = next((u for u in users if u.tenant == tenant), None)
        if chosen is None and not allow_fallback:
            raise AppError("permission_denied", "Invalid username or password")
    if chosen is None and login.current is not None:
        chosen = next((u for u in users if u.tenant == login.current), None)
    if chosen is None:
        chosen = users[0]
    login.current = chosen.tenant
    _touch(login)
    return chosen


def list_login_tenants(session: Session, *, base_id: int) -> list[dict[str, Any]]:
    """Tenants where this login has an active user membership."""
    users = list(
        session.scalars(
            select(SystemUser)
            .where(SystemUser.base_id == base_id)
            .order_by(SystemUser.tenant, SystemUser.id)
        )
    )
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for user in users:
        if not user.active:
            continue
        tid = int(user.tenant)
        if tid in seen:
            continue
        tenant = session.get(SystemTenant, tid)
        if tenant is None:
            continue
        seen.add(tid)
        out.append({"id": tid, "name": tenant.name})
    return out


def switch_login_tenant(
    session: Session, *, base_id: int, tenant_id: int
) -> SystemUser:
    """Switch login.current to another tenant membership; returns that tenant's user."""
    row = session.scalar(
        _user_query(session).where(
            SystemUser.base_id == base_id,
            SystemUser.tenant == tenant_id,
        )
    )
    if row is None or not row.active:
        raise AppError("not_found", "No membership in that tenant")
    login = session.get(SystemLogin, base_id)
    if login is None:
        raise AppError("not_found", "Login not found")
    login.current = tenant_id
    _touch(login)
    session.flush()
    return row


def _new_token_value() -> str:
    return secrets.token_urlsafe(32)


def _agent_token_query(session: Session, user: SystemUser):
    return (
        select(SystemToken)
        .where(
            SystemToken.tenant == user.tenant,
            SystemToken.user_id == user.id,
            SystemToken.kind == TOKEN_KIND_AGENT,
            SystemToken.state == STATE_ON,
        )
        .order_by(SystemToken.id.asc())
    )


def ensure_agent_token(session: Session, user: SystemUser) -> SystemToken:
    """Ensure this tenant-user has an active agent token in ``base_token``."""
    row = session.scalars(_agent_token_query(session, user).limit(1)).first()
    if row is not None and (row.token or "").strip():
        return row
    if row is None:
        row = SystemToken(
            tenant=user.tenant,
            user_id=user.id,
            name="MCP Agent",
            kind=TOKEN_KIND_AGENT,
            token=_new_token_value(),
            extra={"readonly": True},
            state=STATE_ON,
        )
        session.add(row)
    else:
        row.token = _new_token_value()
        if "readonly" not in row.extra_dict():
            row.set_readonly(True)
    _touch(row)
    session.flush()
    return row


def ensure_agent_key(session: Session, user: SystemUser) -> str:
    """Compat: return agent token string (stored in ``base_token``)."""
    return str(ensure_agent_token(session, user).token)


def rotate_agent_key(session: Session, user: SystemUser) -> str:
    """Rotate agent token value (keeps extra / kind)."""
    row = ensure_agent_token(session, user)
    row.token = _new_token_value()
    _touch(row)
    session.flush()
    return str(row.token)


def set_agent_readonly(session: Session, user: SystemUser, readonly: bool) -> bool:
    """Toggle read-only on this user’s agent token (``base_token.extra.readonly``)."""
    row = ensure_agent_token(session, user)
    row.set_readonly(readonly)
    _touch(row)
    session.flush()
    return row.is_readonly()


def get_agent_token(session: Session, user: SystemUser) -> SystemToken | None:
    return session.scalars(_agent_token_query(session, user).limit(1)).first()


def find_token_by_value(
    session: Session, key: str, *, kind: str | None = TOKEN_KIND_AGENT
) -> tuple[SystemToken, SystemUser] | None:
    """Resolve active token (+ owner user) by secret value."""
    raw = (key or "").strip()
    if not raw:
        return None
    stmt = select(SystemToken).where(
        SystemToken.token == raw,
        SystemToken.state == STATE_ON,
    )
    if kind:
        stmt = stmt.where(SystemToken.kind == kind)
    tok = session.scalars(stmt.limit(1)).first()
    if tok is None:
        return None
    if tok.expires_at is not None and tok.expires_at <= _now():
        return None
    user = session.scalar(_user_query(session).where(SystemUser.id == tok.user_id).limit(1))
    if user is None or not user.active or user.tenant != tok.tenant:
        return None
    tok.last_used_at = _now()
    return tok, user


def find_user_by_agent_key(session: Session, key: str) -> SystemUser | None:
    """Resolve active tenant-user by agent token (HTTP MCP auth)."""
    hit = find_token_by_value(session, key, kind=TOKEN_KIND_AGENT)
    if hit is None:
        return None
    return hit[1]


def resolve_agent_auth(session: Session, key: str) -> tuple[SystemUser, bool] | None:
    """Return (user, readonly) for an agent token, or None."""
    hit = find_token_by_value(session, key, kind=TOKEN_KIND_AGENT)
    if hit is None:
        return None
    tok, user = hit
    return user, tok.is_readonly()


# ---------------------------------------------------------------------------
# base_config 模型 — 表名 base_cfg（mod + type + data）
# ---------------------------------------------------------------------------

# 模块 OPTIONAL 字典统一存一行：mod=<module> · type=dict · data={ fieldKey: {title, options} }
CFG_TYPE_DICT = "dict"
# 列表列宽：mod=<module> · type=table.layout · data={ model: { using: { widths } } }
# 列顺序与隐藏列在 base_tbl，不写这里。
CFG_TYPE_TABLE_LAYOUT = "table.layout"

# 种子迁移时勿删的保留 type
_CFG_TYPES_KEEP = frozenset({CFG_TYPE_DICT, CFG_TYPE_TABLE_LAYOUT, "price.rules", "formula"})


class BaseConfig(Base):
    """全局配置行（模型 base_config）。

    - 字典总表：type=dict，data 为 { key: { title, options:[{uukey,value,parent}] } }
    - 其它配置：type 自定，data 可为 list / object
    """

    __tablename__ = "base_cfg"
    __table_args__ = (
        UniqueConstraint("tenant", "mod", "type", name="uq_base_cfg_tenant_mod_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    mod: Mapped[str] = mapped_column(String(64), index=True, default="")
    type: Mapped[str] = mapped_column(String(128), index=True, default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    data: Mapped[Any] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def normalize_dict_options(raw: Any) -> list[dict[str, str]]:
    """规范化字典项：必须含 uukey / value / parent。"""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        uukey = str(item.get("uukey") or item.get("value") or "").strip()
        if not uukey:
            continue
        value = str(item.get("value") or item.get("label") or uukey).strip()
        parent = str(item.get("parent") or "").strip()
        out.append({"uukey": uukey, "value": value, "parent": parent})
    return out


def normalize_dict_bundle(raw: Any) -> dict[str, Any]:
    """规范化整包字典：{ key: { title, options:[{uukey,value,parent}] } }。"""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, meta in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        if isinstance(meta, list):
            out[k] = {
                "title": k,
                "depends": "",
                "hidden": False,
                "options": normalize_dict_options(meta),
            }
            continue
        if not isinstance(meta, dict):
            continue
        opts = meta.get("options")
        if opts is None and any(x in meta for x in ("uukey", "value", "label")):
            opts = [meta]
        out[k] = {
            "title": str(meta.get("title") or k),
            "depends": str(meta.get("depends") or ""),
            "hidden": bool(meta.get("hidden")),
            "options": normalize_dict_options(opts or []),
        }
    return out


def normalize_table_layout(raw: Any) -> dict[str, Any]:
    """规范化 table.layout：{ model: { using: { widths: { fieldKey: number } } } }。"""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for model, views in raw.items():
        mk = str(model or "").strip()
        if not mk or not isinstance(views, dict):
            continue
        view_out: dict[str, Any] = {}
        for using, meta in views.items():
            uk = str(using or "").strip() or "default"
            widths_raw: Any
            if isinstance(meta, dict) and "widths" in meta:
                widths_raw = meta.get("widths")
            elif isinstance(meta, dict):
                # 允许直接 { "basic.plate": 120 } 简写
                widths_raw = meta
            else:
                continue
            if not isinstance(widths_raw, dict):
                continue
            widths: dict[str, int] = {}
            for fk, w in widths_raw.items():
                key = str(fk or "").strip()
                if not key or key in ("widths", "columns"):
                    continue
                try:
                    n = int(round(float(w)))
                except (TypeError, ValueError):
                    continue
                if n < 40:
                    continue
                widths[key] = n
            if widths:
                view_out[uk] = {"widths": widths}
        if view_out:
            out[mk] = view_out
    return out


def config_row(row: BaseConfig) -> dict[str, Any]:
    data: Any
    if str(row.type or "") == CFG_TYPE_DICT:
        data = normalize_dict_bundle(row.data)
    elif str(row.type or "") == CFG_TYPE_TABLE_LAYOUT:
        data = normalize_table_layout(row.data)
    elif isinstance(row.data, list):
        data = normalize_dict_options(row.data)
    else:
        data = row.data
    return {
        "id": row.id,
        "mod": row.mod,
        "type": row.type,
        "title": row.title or row.type,
        "data": data,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_config(
    session: Session, ctx: Ctx, *, mod: str, type: str
) -> BaseConfig | None:
    m = str(mod or "").strip()
    t = str(type or "").strip()
    if not m or not t:
        return None
    return session.scalar(
        select(BaseConfig)
        .where(
            BaseConfig.tenant == ctx.tenant,
            BaseConfig.mod == m,
            BaseConfig.type == t,
        )
        .limit(1)
    )


def list_configs(
    session: Session, ctx: Ctx, *, mod: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(BaseConfig).where(BaseConfig.tenant == ctx.tenant)
    if mod:
        stmt = stmt.where(BaseConfig.mod == str(mod).strip())
    rows = session.scalars(stmt.order_by(BaseConfig.mod.asc(), BaseConfig.type.asc())).all()
    return [config_row(r) for r in rows]


def upsert_config(
    session: Session,
    ctx: Ctx,
    *,
    mod: str,
    type: str,
    data: Any,
    title: str | None = None,
) -> dict[str, Any]:
    m = str(mod or "").strip()
    t = str(type or "").strip()
    if not m or not t:
        raise AppError("validation_error", "mod and type required")
    if t == CFG_TYPE_DICT:
        payload: Any = normalize_dict_bundle(data)
    elif t == CFG_TYPE_TABLE_LAYOUT:
        payload = normalize_table_layout(data)
    elif isinstance(data, list):
        payload = normalize_dict_options(data)
    else:
        payload = data
    row = get_config(session, ctx, mod=m, type=t)
    now = datetime.now(timezone.utc)
    if row is None:
        default_title = "字典设置" if t == CFG_TYPE_DICT else ("表格布局" if t == CFG_TYPE_TABLE_LAYOUT else t)
        row = BaseConfig(
            id=str(uuid.uuid4()),
            tenant=ctx.tenant,
            mod=m,
            type=t,
            title=str(title or default_title),
            data=payload,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.data = payload
        if title is not None:
            row.title = str(title)
        row.updated_at = now
    session.flush()
    return config_row(row)


def delete_config(session: Session, ctx: Ctx, *, mod: str, type: str) -> bool:
    row = get_config(session, ctx, mod=mod, type=type)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def get_dict_bundle(session: Session, ctx: Ctx, *, mod: str) -> dict[str, Any]:
    row = get_config(session, ctx, mod=mod, type=CFG_TYPE_DICT)
    return normalize_dict_bundle(row.data if row else {})


def list_dict_options(
    session: Session, ctx: Ctx, *, mod: str, type: str
) -> list[dict[str, Any]]:
    """OPTIONAL refers：从 mod 的唯一 dict 包里取 type(=fieldKey) 的 options。"""
    bundle = get_dict_bundle(session, ctx, mod=mod)
    meta = bundle.get(str(type or "").strip()) or {}
    opts = normalize_dict_options(meta.get("options") if isinstance(meta, dict) else [])
    return [
        {
            "uukey": o["uukey"],
            "label": o["value"],
            "value": o["value"],
            "parent": o["parent"],
        }
        for o in opts
    ]


def ensure_config_seeded(
    session: Session,
    ctx: Ctx,
    *,
    mod: str,
    catalog: dict[str, Any],
) -> int:
    """把 catalog 灌进唯一一行 (mod, type=dict)。已有则补缺失 key；顺带合并旧散装行。"""
    m = str(mod or "").strip()
    if not m or not catalog:
        return 0
    bundle = normalize_dict_bundle(catalog)

    legacy = session.scalars(
        select(BaseConfig).where(
            BaseConfig.tenant == ctx.tenant,
            BaseConfig.mod == m,
            BaseConfig.type != CFG_TYPE_DICT,
            BaseConfig.type != "price.rules",
            BaseConfig.type != "formula",
        )
    ).all()
    for row in legacy:
        t = str(row.type or "").strip()
        if not t or t.startswith("price.") or t == "formula":
            continue
        if t in bundle:
            continue
        if isinstance(row.data, list):
            bundle[t] = {
                "title": str(row.title or t),
                "depends": "",
                "options": normalize_dict_options(row.data),
            }
        elif isinstance(row.data, dict) and "options" in row.data:
            bundle[t] = normalize_dict_bundle({t: row.data})[t]

    existing = get_config(session, ctx, mod=m, type=CFG_TYPE_DICT)
    if existing is not None:
        cur = normalize_dict_bundle(existing.data)
        added = 0
        for k, meta in bundle.items():
            if k not in cur:
                cur[k] = meta
                added += 1
                continue
            # 补 depends / hidden / 缺失 option；空 parent 用 catalog 回填（不覆盖已有 parent）
            cat_dep = str(meta.get("depends") or "")
            if cat_dep and not str(cur[k].get("depends") or ""):
                cur[k]["depends"] = cat_dep
                added += 1
            if bool(meta.get("hidden")) and not cur[k].get("hidden"):
                cur[k]["hidden"] = True
                added += 1
            cat_opts = {
                str(o.get("uukey")): o
                for o in (meta.get("options") or [])
                if isinstance(o, dict) and o.get("uukey")
            }
            cur_opts = list(cur[k].get("options") or [])
            by_key = {
                str(o.get("uukey")): o
                for o in cur_opts
                if isinstance(o, dict) and o.get("uukey")
            }
            for uk, co in cat_opts.items():
                if uk not in by_key:
                    cur_opts.append(dict(co))
                    by_key[uk] = cur_opts[-1]
                    added += 1
                elif co.get("parent") and not str(by_key[uk].get("parent") or ""):
                    by_key[uk]["parent"] = co["parent"]
                    added += 1
            cur[k]["options"] = cur_opts
        if added:
            existing.data = cur
            existing.updated_at = datetime.now(timezone.utc)
            session.flush()
        for row in legacy:
            t = str(row.type or "").strip()
            if t and t not in _CFG_TYPES_KEEP and not t.startswith("price."):
                session.delete(row)
        if legacy:
            session.flush()
        return added

    now = datetime.now(timezone.utc)
    session.add(
        BaseConfig(
            id=str(uuid.uuid4()),
            tenant=ctx.tenant,
            mod=m,
            type=CFG_TYPE_DICT,
            title="字典设置",
            data=bundle,
            created_at=now,
            updated_at=now,
        )
    )
    for row in legacy:
        t = str(row.type or "").strip()
        if t and t not in _CFG_TYPES_KEEP and not t.startswith("price."):
            session.delete(row)
    session.flush()
    return len(bundle)


def parse_dict_key(dict_key: str) -> tuple[str, str] | None:
    """dictKey → (mod, fieldKey)。fleet:vehicle.energy → ('fleet','vehicle.energy')。"""
    raw = str(dict_key or "").strip()
    if not raw or ":" not in raw:
        return None
    mod, typ = raw.split(":", 1)
    mod, typ = mod.strip(), typ.strip()
    if not mod or not typ:
        return None
    return mod, typ


# Register base_serial / base_tbl on Base.metadata (create_all).
from builtin.base.tbl import BaseTbl as BaseTbl  # noqa: E402, F401
from builtin.base.serial import (  # noqa: E402
    BaseSerial as BaseSerial,
    alloc_serial as alloc_serial,
    ensure_serial_at_least as ensure_serial_at_least,
    reserve_serials as reserve_serials,
    serial_date_stamp as serial_date_stamp,
)
