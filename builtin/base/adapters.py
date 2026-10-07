"""Base model adapters: schema index ↔ domain ORM."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.core.state import STATE_OFF, STATE_ON
from modoor.engine.adapters import (
    ModelAdapter,
    flatten_pick,
    normalize_batch_row,
    register_adapter,
)
from modoor.engine.oplog import diff_row_values, record_oplog
from modoor.engine.query import QueryTerm, parse_query

# Ensure SystemOplog writer is registered on modoor.engine.oplog.
import builtin.base.domain  # noqa: F401


def _parse_datetime(val: Any) -> datetime | None:
    if val in (None, ""):
        return None
    s = str(val).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise AppError("validation_error", f"invalid datetime: {val}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _truthy_on(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val) == STATE_ON
    return str(val).strip().lower() in ("1", "true", "yes", "y", "active", "on")


def _as_on_off(val: Any) -> int | list[int]:
    if isinstance(val, list):
        return [STATE_ON if _truthy_on(v) else STATE_OFF for v in val]
    return STATE_ON if _truthy_on(val) else STATE_OFF


class SystemUserAdapter(ModelAdapter):
    model = "base.user"

    COLS: dict[str, str] = {
        "basic.code": "code",
        "basic.utime": "utime",
        "basic.name": "name",
        "basic.phone": "phone",
        "basic.email": "email",
        "basic.remark": "remark",
        "basic.team_id": "team_id",
        "basic.model": "model",
        "basic.refer": "refer",
    }

    def _to_values(self, user: Any, field_keys: list[str] | None = None) -> dict[str, Any]:
        raw = {
            "basic.code": user.code,
            "basic.utime": user.utime.isoformat() if user.utime else None,
            "basic.state": str(int(user.state or 0)),
            "basic.enable": str(int(user.enable or 0)),
            "basic.username": user.username,
            "basic.realname": user.realname,
            "basic.name": user.name or "",
            "basic.phone": user.phone or "",
            "basic.email": user.email or "",
            "basic.remark": user.remark or "",
            "basic.model": user.model or "",
            "basic.refer": user.refer or "",
            "basic.active": "true" if user.active else "false",
            "basic.team_id": str(user.team_id) if user.team_id is not None else "",
        }
        if field_keys is None:
            return raw
        return {k: raw.get(k) for k in field_keys if k in raw}

    def _apply_terms(self, stmt: Any, terms: list[QueryTerm]) -> Any:
        from builtin.base.domain import SystemLogin, SystemUser

        for term in terms:
            op = term.op
            val = term.value
            if term.field == "basic.username":
                col = SystemLogin.username
            elif term.field == "basic.realname":
                col = SystemLogin.realname
            elif term.field in ("basic.active", "basic.enable"):
                col = SystemUser.enable
                val = _as_on_off(val)
            elif term.field == "basic.state":
                col = SystemUser.state
                val = _as_on_off(val)
            else:
                col_name = self.COLS.get(term.field)
                if not col_name:
                    continue
                col = getattr(SystemUser, col_name)
            if term.field == "basic.team_id" and val is not None and not isinstance(val, list):
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    pass
            if term.field == "basic.team_id" and isinstance(val, list):
                casted = []
                for v in val:
                    try:
                        casted.append(int(v))
                    except (TypeError, ValueError):
                        casted.append(v)
                val = casted
            if op == "EQ":
                stmt = stmt.where(col == val)
            elif op == "NE":
                stmt = stmt.where(col != val)
            elif op == "IN":
                vals = val if isinstance(val, list) else [val]
                stmt = stmt.where(col.in_(vals))
            elif op == "LIKE":
                stmt = stmt.where(col.ilike(f"%{val}%") if hasattr(col, "ilike") else col.like(f"%{val}%"))
            elif op == "NIL":
                if val in (True, "true", 1, "1"):
                    stmt = stmt.where(col.is_(None))
                else:
                    stmt = stmt.where(col.is_not(None))
        return stmt

    def search(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        order: dict[str, Any] | None,
        page: int,
        size: int,
        field_keys: list[str],
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
        from builtin.base.domain import SystemLogin, SystemUser

        page = max(int(page or 1), 1)
        size = min(max(int(size or 50), 1), 500)
        terms = parse_query(query)
        base = (
            select(SystemUser)
            .options(selectinload(SystemUser.login))
            .join(SystemLogin, SystemUser.base_id == SystemLogin.id)
            .where(SystemUser.tenant == ctx.tenant)
        )
        if not any(t.field in ("basic.state", "basic.active", "basic.enable") for t in terms):
            base = base.where(SystemUser.state == STATE_ON)
        base = self._apply_terms(base, terms)

        count = session.scalar(select(func.count()).select_from(base.subquery())) or 0

        order_field = (order or {}).get("field") or "basic.username"
        order_dir = str((order or {}).get("order") or "asc").lower()
        if order_field == "basic.username":
            col: Any = SystemLogin.username
        elif order_field == "basic.realname":
            col = SystemLogin.realname
        elif order_field == "basic.active" or order_field == "basic.enable":
            col = SystemUser.enable
        else:
            col_name = self.COLS.get(str(order_field), "code")
            col = getattr(SystemUser, col_name, SystemUser.code)
        ordered = base.order_by(desc(col) if order_dir == "desc" else asc(col))
        rows = list(session.scalars(ordered.offset((page - 1) * size).limit(size)))
        values = [self._to_values(r, field_keys) for r in rows]
        return values, int(count), None

    def refers(self, session: Session, ctx: Ctx) -> dict[str, Any]:
        from builtin.base import domain as base_domain

        return {"basic.team_id": base_domain.list_team_options(session, ctx)}

    def _get_entity(self, session: Session, ctx: Ctx, uukey: str):
        from builtin.base.domain import SystemUser

        stmt = (
            select(SystemUser)
            .options(selectinload(SystemUser.login))
            .where(SystemUser.tenant == ctx.tenant)
        )
        row = session.scalar(stmt.where(SystemUser.code == uukey))
        if row is None and uukey.isdigit():
            row = session.scalar(stmt.where(SystemUser.id == int(uukey)))
        return row

    def get_values(self, session: Session, ctx: Ctx, uukey: str) -> dict[str, Any] | None:
        user = self._get_entity(session, ctx, uukey)
        if user is None:
            return None
        return self._to_values(user)

    def upsert(
        self,
        session: Session,
        ctx: Ctx,
        batch: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from builtin.base import domain as base_domain

        records: list[dict[str, Any]] = []
        for raw in batch:
            row = normalize_batch_row(raw)
            uukey = str(row.get("basic.code") or row.get("basic.uukey") or row.get("code") or row.get("uukey") or "").strip()
            username = str(flatten_pick(row, "basic.username") or "").strip()
            realname = str(flatten_pick(row, "basic.realname") or "").strip()
            name = str(flatten_pick(row, "basic.name") or "").strip()
            phone = flatten_pick(row, "basic.phone")
            email = flatten_pick(row, "basic.email")
            remark = flatten_pick(row, "basic.remark")
            password = flatten_pick(row, "basic.password")
            team_raw = flatten_pick(row, "basic.team_id")
            utime = _parse_datetime(flatten_pick(row, "basic.utime"))
            model = flatten_pick(row, "basic.model")
            refer = flatten_pick(row, "basic.refer")

            team_id: int | None = None
            if team_raw not in (None, ""):
                team_id = int(team_raw)

            existing = self._get_entity(session, ctx, uukey) if uukey else None
            if existing:
                before = self._to_values(existing)
                kwargs: dict[str, Any] = {"user_id": existing.id}
                if realname:
                    kwargs["realname"] = realname
                if name:
                    kwargs["name"] = name
                if phone is not None:
                    kwargs["phone"] = str(phone) if phone != "" else ""
                if remark is not None:
                    kwargs["remark"] = str(remark) if remark != "" else ""
                if email is not None:
                    kwargs["email"] = str(email) if email != "" else ""
                if team_id is not None:
                    kwargs["team_id"] = team_id
                if utime is not None:
                    kwargs["utime"] = utime
                if model is not None:
                    kwargs["model"] = str(model)
                if refer is not None:
                    kwargs["refer"] = str(refer)
                if password not in (None, ""):
                    kwargs["password"] = str(password)
                updated = base_domain.update_user(session, ctx, **kwargs)
                entity = self._get_entity(session, ctx, updated["uukey"])
                assert entity is not None
                current = self._to_values(entity)
                changes = diff_row_values(before, current)
                if changes:
                    record_oplog(
                        session,
                        ctx,
                        code=entity.uukey,
                        action="UPDATE",
                        model=self.model,
                        before=before,
                        after=current,
                        diff=changes,
                    )
                records.append(
                    {
                        "uukey": entity.uukey,
                        "model": self.model,
                        "opType": "UPDATE",
                        "exists": True,
                        "request": row,
                        "current": current,
                        "prepare": current,
                        "storage": {"basic": current},
                        "changed": bool(changes),
                        "changes": changes,
                        "objects": None,
                    }
                )
                continue

            if not name and not realname:
                raise AppError("validation_error", "name is required")
            display_name = name or realname
            created = base_domain.create_user(
                session,
                ctx,
                username=username or None,
                realname=realname or display_name,
                name=display_name,
                phone=str(phone).strip() if phone not in (None, "") else None,
                email=str(email).strip() if email not in (None, "") else None,
                remark=str(remark).strip() if remark not in (None, "") else None,
                password=str(password) if password not in (None, "") else None,
                team_id=team_id if team_id is not None else ctx.team_id,
                utime=utime,
                code=uukey or None,
                model=str(model) if model not in (None, "") else None,
                refer=str(refer) if refer not in (None, "") else None,
            )
            entity = self._get_entity(session, ctx, created["uukey"])
            assert entity is not None
            current = self._to_values(entity)
            changes = diff_row_values(None, current)
            record_oplog(
                session,
                ctx,
                code=entity.uukey,
                action="INSERT",
                model=self.model,
                before=None,
                after=current,
                diff=changes,
            )
            records.append(
                {
                    "uukey": entity.uukey,
                    "model": self.model,
                    "opType": "INSERT",
                    "exists": False,
                    "request": row,
                    "current": current,
                    "prepare": current,
                    "storage": {"basic": current},
                    "changed": True,
                    "changes": changes,
                    "objects": None,
                }
            )
        return records

    def delete_keys(self, session: Session, ctx: Ctx, keys: list[str]) -> None:
        from builtin.base import domain as base_domain

        for key in keys:
            entity = self._get_entity(session, ctx, str(key).strip())
            if entity is None:
                continue
            if entity.id == ctx.user_id:
                raise AppError("validation_error", "cannot delete the current user")
            before = self._to_values(entity)
            code = entity.uukey
            try:
                base_domain.delete_user(session, ctx, user_id=entity.id)
            except AppError as exc:
                if exc.code == "not_found":
                    continue
                raise
            record_oplog(
                session,
                ctx,
                code=code,
                action="DELETE",
                model=self.model,
                before=before,
                after=None,
            )


def ensure_base_adapters() -> None:
    from modoor.engine import adapters as eng

    if "base.user" not in eng._ADAPTERS:
        register_adapter(SystemUserAdapter())


ensure_base_adapters()
