"""builtin.flow — automation / workflow / approval ORM + APIs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError

from builtin.flow.jobs import register as register_jobs

register_jobs()

MODULE_ID = "flow"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class FlowDefinition(Base):
    __tablename__ = "flow_definition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|published
    version: Mapped[int] = mapped_column(Integer, default=1)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    updated_by: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class FlowInstance(Base):
    __tablename__ = "flow_instance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    definition_id: Mapped[str] = mapped_column(String(36), index=True)
    definition_key: Mapped[str] = mapped_column(String(128), index=True, default="")
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    current_node: Mapped[str] = mapped_column(String(128), default="")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ref_model: Mapped[str] = mapped_column(String(128), default="")
    ref_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class FlowTask(Base):
    __tablename__ = "flow_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    instance_id: Mapped[str] = mapped_column(String(36), index=True)
    node_id: Mapped[str] = mapped_column(String(128), default="")
    level: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    assignee_role: Mapped[str] = mapped_column(String(64), default="")
    assignee_user: Mapped[int] = mapped_column(Integer, default=0)
    form: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(32), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int] = mapped_column(Integer, default=0)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class FlowRunLog(Base):
    __tablename__ = "flow_run_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    instance_id: Mapped[str] = mapped_column(String(36), index=True)
    node_id: Mapped[str] = mapped_column(String(128), default="")
    event: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FlowSchedule(Base):
    __tablename__ = "flow_schedule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    flow_key: Mapped[str] = mapped_column(String(128), index=True)
    cron: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


def _def_dict(row: FlowDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "title": row.title,
        "status": row.status,
        "version": row.version,
        "graph": row.graph or {},
        "trigger": row.trigger or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _inst_dict(row: FlowInstance) -> dict[str, Any]:
    return {
        "id": row.id,
        "definition_id": row.definition_id,
        "definition_key": row.definition_key,
        "status": row.status,
        "current_node": row.current_node,
        "context": row.context or {},
        "ref_model": row.ref_model,
        "ref_id": row.ref_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _task_dict(row: FlowTask) -> dict[str, Any]:
    return {
        "id": row.id,
        "instance_id": row.instance_id,
        "node_id": row.node_id,
        "level": row.level,
        "title": row.title,
        "status": row.status,
        "assignee_role": row.assignee_role,
        "assignee_user": row.assignee_user,
        "form": row.form or {},
        "decision": row.decision,
        "comment": row.comment,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_definitions(session: Session, ctx: Ctx) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(FlowDefinition)
            .where(FlowDefinition.tenant == ctx.tenant)
            .order_by(FlowDefinition.key, FlowDefinition.version.desc())
        )
    )
    return {"items": [_def_dict(r) for r in rows], "count": len(rows)}


def get_definition(
    session: Session, ctx: Ctx, *, definition_id: str | None = None, key: str | None = None
) -> dict[str, Any]:
    row = _load_definition(session, ctx, definition_id=definition_id, key=key)
    return _def_dict(row)


def _load_definition(
    session: Session,
    ctx: Ctx,
    *,
    definition_id: str | None = None,
    key: str | None = None,
    published_only: bool = False,
) -> FlowDefinition:
    if definition_id:
        row = session.get(FlowDefinition, definition_id)
        if row is None or row.tenant != ctx.tenant:
            raise AppError("not_found", "flow definition not found")
        return row
    if not key:
        raise AppError("validation_error", "definition_id or key required")
    stmt = (
        select(FlowDefinition)
        .where(FlowDefinition.tenant == ctx.tenant, FlowDefinition.key == key)
        .order_by(FlowDefinition.version.desc())
    )
    if published_only:
        stmt = stmt.where(FlowDefinition.status == "published")
    row = session.scalars(stmt).first()
    if row is None:
        raise AppError("not_found", f"flow definition not found: {key}")
    return row


def upsert_definition(
    session: Session,
    ctx: Ctx,
    *,
    key: str,
    title: str,
    graph: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
    status: str = "draft",
    definition_id: str | None = None,
) -> dict[str, Any]:
    key = (key or "").strip()
    if not key:
        raise AppError("validation_error", "key required")
    if definition_id:
        row = _load_definition(session, ctx, definition_id=definition_id)
        row.title = title or row.title
        row.graph = graph if graph is not None else row.graph
        row.trigger = trigger if trigger is not None else row.trigger
        row.status = status or row.status
        row.updated_by = ctx.user_id
        row.updated_at = _now()
    else:
        existing = session.scalars(
            select(FlowDefinition)
            .where(FlowDefinition.tenant == ctx.tenant, FlowDefinition.key == key)
            .order_by(FlowDefinition.version.desc())
        ).first()
        version = int(existing.version) + 1 if existing else 1
        row = FlowDefinition(
            id=_new_id(),
            tenant=ctx.tenant,
            key=key,
            title=title or key,
            status=status or "draft",
            version=version,
            graph=graph or {},
            trigger=trigger or {},
            created_by=ctx.user_id,
            updated_by=ctx.user_id,
        )
        session.add(row)
    session.flush()
    return _def_dict(row)


def publish_definition(session: Session, ctx: Ctx, *, definition_id: str) -> dict[str, Any]:
    row = _load_definition(session, ctx, definition_id=definition_id)
    row.status = "published"
    row.updated_by = ctx.user_id
    row.updated_at = _now()
    session.flush()
    return _def_dict(row)


def list_instances(
    session: Session,
    ctx: Ctx,
    *,
    status: str | None = None,
    definition_key: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    stmt = (
        select(FlowInstance)
        .where(FlowInstance.tenant == ctx.tenant)
        .order_by(FlowInstance.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if status:
        stmt = stmt.where(FlowInstance.status == status)
    if definition_key:
        stmt = stmt.where(FlowInstance.definition_key == definition_key)
    rows = list(session.scalars(stmt))
    return {"items": [_inst_dict(r) for r in rows], "count": len(rows)}


def get_instance(session: Session, ctx: Ctx, *, instance_id: str) -> dict[str, Any]:
    row = session.get(FlowInstance, instance_id)
    if row is None or row.tenant != ctx.tenant:
        raise AppError("not_found", "flow instance not found")
    logs = list(
        session.scalars(
            select(FlowRunLog)
            .where(FlowRunLog.instance_id == instance_id)
            .order_by(FlowRunLog.created_at.asc())
        )
    )
    tasks = list(
        session.scalars(
            select(FlowTask)
            .where(FlowTask.instance_id == instance_id)
            .order_by(FlowTask.level.asc(), FlowTask.created_at.asc())
        )
    )
    return {
        "instance": _inst_dict(row),
        "logs": [
            {
                "id": l.id,
                "node_id": l.node_id,
                "event": l.event,
                "detail": l.detail or {},
                "error": l.error,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
        "tasks": [_task_dict(t) for t in tasks],
    }


def list_tasks(
    session: Session,
    ctx: Ctx,
    *,
    status: str = "pending",
    limit: int = 100,
) -> dict[str, Any]:
    stmt = (
        select(FlowTask)
        .where(FlowTask.tenant == ctx.tenant)
        .order_by(FlowTask.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if status:
        stmt = stmt.where(FlowTask.status == status)
    rows = list(session.scalars(stmt))
    return {"items": [_task_dict(r) for r in rows], "count": len(rows)}


def list_schedules(session: Session, ctx: Ctx) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(FlowSchedule).where(FlowSchedule.tenant == ctx.tenant)
        )
    )
    return {
        "items": [
            {
                "id": r.id,
                "flow_key": r.flow_key,
                "cron": r.cron,
                "enabled": r.enabled,
                "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None,
                "payload": r.payload or {},
            }
            for r in rows
        ],
        "count": len(rows),
    }


def upsert_schedule(
    session: Session,
    ctx: Ctx,
    *,
    flow_key: str,
    cron: str,
    enabled: bool = True,
    payload: dict[str, Any] | None = None,
    schedule_id: str | None = None,
) -> dict[str, Any]:
    from builtin.flow.schedule import next_cron_time

    if schedule_id:
        row = session.get(FlowSchedule, schedule_id)
        if row is None or row.tenant != ctx.tenant:
            raise AppError("not_found", "schedule not found")
        row.flow_key = flow_key or row.flow_key
        row.cron = cron or row.cron
        row.enabled = enabled
        row.payload = payload if payload is not None else row.payload
    else:
        row = FlowSchedule(
            id=_new_id(),
            tenant=ctx.tenant,
            flow_key=flow_key,
            cron=cron,
            enabled=enabled,
            payload=payload or {},
        )
        session.add(row)
    row.next_run_at = next_cron_time(row.cron) if row.enabled else None
    row.updated_at = _now()
    session.flush()
    return {
        "id": row.id,
        "flow_key": row.flow_key,
        "cron": row.cron,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "payload": row.payload or {},
    }


def append_log(
    session: Session,
    *,
    tenant: int,
    instance_id: str,
    node_id: str,
    event: str,
    detail: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    session.add(
        FlowRunLog(
            id=_new_id(),
            tenant=tenant,
            instance_id=instance_id,
            node_id=node_id,
            event=event,
            detail=detail or {},
            error=error or "",
        )
    )
    session.flush()


def seed_builtin_definitions(session: Session, ctx: Ctx) -> int:
    """Install packaged definitions if missing (idempotent)."""
    root = Path(__file__).resolve().parent / "definitions"
    if not root.is_dir():
        return 0
    added = 0
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        key = str(data.get("key") or path.stem)
        exists = session.scalars(
            select(FlowDefinition).where(
                FlowDefinition.tenant == ctx.tenant,
                FlowDefinition.key == key,
                FlowDefinition.status == "published",
            )
        ).first()
        if exists:
            continue
        upsert_definition(
            session,
            ctx,
            key=key,
            title=str(data.get("title") or key),
            graph=data.get("graph") or {},
            trigger=data.get("trigger") or {},
            status="published",
        )
        added += 1
    return added


def on_enable(session: Session, ctx: Ctx) -> None:
    seed_builtin_definitions(session, ctx)
