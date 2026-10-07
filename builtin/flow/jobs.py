"""Flow job handlers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modoor.runtime.jobs import enqueue, register_handler

_REGISTERED = False


def handle_advance(session: Session, payload: dict[str, Any]) -> None:
    from builtin.flow.engine import advance

    advance(session, instance_id=str(payload.get("instance_id") or ""))


def handle_wait_doc_extract(session: Session, payload: dict[str, Any]) -> None:
    from builtin.doc.domain import DocAsset
    from builtin.flow.engine import advance
    from builtin.flow.domain import FlowInstance

    instance_id = str(payload.get("instance_id") or "")
    asset_id = str(payload.get("asset_id") or "")
    inst = session.get(FlowInstance, instance_id)
    if inst is None:
        return
    asset = session.get(DocAsset, asset_id)
    if asset is None:
        inst.status = "running"
        enqueue(session, kind="flow.advance", payload={"instance_id": instance_id})
        return
    status = asset.text_status or "ready"
    if status in ("pending", "running"):
        enqueue(
            session,
            kind="flow.wait_doc_extract",
            payload={"instance_id": instance_id, "asset_id": asset_id},
        )
        return
    ctx = dict(inst.context or {})
    ctx["doc_text"] = asset.text or ""
    ctx["doc_text_status"] = status
    inst.context = ctx
    inst.status = "running"
    session.flush()
    advance(session, instance_id=instance_id)


def handle_schedule_tick(session: Session, payload: dict[str, Any]) -> None:
    from datetime import timezone
    from datetime import datetime

    from modoor.core.ctx import Ctx
    from builtin.flow.domain import FlowSchedule
    from builtin.flow.engine import start_instance
    from builtin.flow.schedule import cron_matches, next_cron_time

    now = datetime.now(timezone.utc)
    rows = list(
        session.scalars(
            select(FlowSchedule).where(FlowSchedule.enabled.is_(True))
        )
    )
    for row in rows:
        due = row.next_run_at
        if due is not None and due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due is not None and due > now:
            continue
        if due is None and not cron_matches(row.cron, now):
            continue
        ctx = Ctx(tenant=row.tenant, user_id=0, team_id=0)
        try:
            start_instance(
                session,
                ctx,
                definition_key=row.flow_key,
                context=dict(row.payload or {}),
            )
        except Exception:  # noqa: BLE001
            continue
        row.next_run_at = next_cron_time(row.cron, after=now)
        session.flush()


def register() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_handler("flow.advance", handle_advance)
    register_handler("flow.wait_doc_extract", handle_wait_doc_extract)
    register_handler("flow.schedule.tick", handle_schedule_tick)
    _REGISTERED = True
