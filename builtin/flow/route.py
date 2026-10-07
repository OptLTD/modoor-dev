"""builtin.flow JSON API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from modoor.core.db import session_scope
from modoor.web.api_util import ctx_of, http_error, require_user
from builtin.flow import domain as flow_domain
from builtin.flow import engine as flow_engine

router = APIRouter(prefix="/api/flow", tags=["flow"])


class DefinitionUpsert(BaseModel):
    key: str
    title: str = ""
    graph: dict[str, Any] = Field(default_factory=dict)
    trigger: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"
    definition_id: str | None = None


class TaskDecide(BaseModel):
    decision: str
    comment: str = ""


class EmitBody(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduleUpsert(BaseModel):
    flow_key: str
    cron: str
    enabled: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    schedule_id: str | None = None


@router.get("/definitions")
def api_list_definitions(request: Request) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return flow_domain.list_definitions(session, ctx_of(user))
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/definitions/{definition_id}")
def api_get_definition(request: Request, definition_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return {
                "definition": flow_domain.get_definition(
                    session, ctx_of(user), definition_id=definition_id
                )
            }
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/definitions")
def api_upsert_definition(request: Request, body: DefinitionUpsert) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            item = flow_domain.upsert_definition(
                session,
                ctx_of(user),
                key=body.key,
                title=body.title,
                graph=body.graph,
                trigger=body.trigger,
                status=body.status,
                definition_id=body.definition_id,
            )
            return {"ok": True, "definition": item}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/definitions/{definition_id}/publish")
def api_publish(request: Request, definition_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            item = flow_domain.publish_definition(
                session, ctx_of(user), definition_id=definition_id
            )
            return {"ok": True, "definition": item}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/instances")
def api_list_instances(
    request: Request,
    status: str | None = None,
    definition_key: str | None = None,
) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return flow_domain.list_instances(
                session,
                ctx_of(user),
                status=status,
                definition_key=definition_key,
            )
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/instances/{instance_id}")
def api_get_instance(request: Request, instance_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return flow_domain.get_instance(session, ctx_of(user), instance_id=instance_id)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/tasks")
def api_list_tasks(request: Request, status: str = "pending") -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return flow_domain.list_tasks(session, ctx_of(user), status=status)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/tasks/{task_id}/decide")
def api_decide(request: Request, task_id: str, body: TaskDecide) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            task = flow_engine.decide_task(
                session,
                ctx_of(user),
                task_id=task_id,
                decision=body.decision,
                comment=body.comment,
            )
            return {"ok": True, "task": task}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/emit")
def api_emit(request: Request, body: EmitBody) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            inst = flow_engine.emit(
                session,
                ctx_of(user),
                event_type=body.event_type,
                payload=body.payload,
            )
            return {"ok": True, "instance": inst}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/schedules")
def api_list_schedules(request: Request) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return flow_domain.list_schedules(session, ctx_of(user))
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/schedules")
def api_upsert_schedule(request: Request, body: ScheduleUpsert) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            item = flow_domain.upsert_schedule(
                session,
                ctx_of(user),
                flow_key=body.flow_key,
                cron=body.cron,
                enabled=body.enabled,
                payload=body.payload,
                schedule_id=body.schedule_id,
            )
            return {"ok": True, "schedule": item}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


def register(app, kit) -> None:  # noqa: ANN001
    app.include_router(router)
