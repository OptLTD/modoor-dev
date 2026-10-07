"""builtin.wiki JSON API — projects, tree, pages (id-only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from modoor.core.db import session_scope
from modoor.web.api_util import ctx_of, http_error, require_user
from builtin.wiki import domain as wiki_domain

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    home_title: str = "Home"


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PageCreate(BaseModel):
    project_id: str
    title: str
    body: str | None = None
    parent_id: str | None = None


class PageUpdate(BaseModel):
    title: str | None = None
    body: str | None = None


class PageMove(BaseModel):
    parent_id: str | None = None
    sort_order: int | None = None


@router.get("/projects")
def api_list_projects(request: Request) -> dict[str, Any]:
    user = require_user(request)
    with session_scope() as session:
        return wiki_domain.list_projects(session, ctx_of(user))


@router.post("/projects")
def api_create_project(request: Request, body: ProjectCreate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            result = wiki_domain.create_project(
                session,
                ctx_of(user),
                name=body.name,
                description=body.description,
                home_title=body.home_title,
            )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/projects/{project_id}")
def api_get_project(request: Request, project_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return {"project": wiki_domain.get_project(session, ctx_of(user), project_id=project_id)}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.patch("/projects/{project_id}")
def api_update_project(request: Request, project_id: str, body: ProjectUpdate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            project = wiki_domain.update_project(
                session,
                ctx_of(user),
                project_id=project_id,
                name=body.name,
                description=body.description,
            )
        return {"ok": True, "project": project}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/projects/{project_id}")
def api_delete_project(request: Request, project_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            result = wiki_domain.delete_project(session, ctx_of(user), project_id=project_id)
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/projects/{project_id}/tree")
def api_project_tree(request: Request, project_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return wiki_domain.get_tree(session, ctx_of(user), project_id=project_id)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/pages")
def api_list_pages(request: Request, project_id: str | None = None, q: str | None = None) -> dict[str, Any]:
    user = require_user(request)
    with session_scope() as session:
        return wiki_domain.list_pages(
            session, ctx_of(user), project_id=project_id, q=q, limit=200
        )


@router.post("/pages")
def api_create_page(request: Request, body: PageCreate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            page = wiki_domain.create_page(
                session,
                ctx_of(user),
                project_id=body.project_id,
                title=body.title,
                body=body.body,
                parent_id=body.parent_id,
            )
        return {"ok": True, "page": page}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/pages/{page_id}")
def api_get_page(request: Request, page_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return {"page": wiki_domain.get_page(session, ctx_of(user), page_id=page_id)}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.patch("/pages/{page_id}")
def api_update_page(request: Request, page_id: str, body: PageUpdate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            page = wiki_domain.update_page(
                session,
                ctx_of(user),
                page_id=page_id,
                title=body.title,
                body=body.body,
            )
        return {"ok": True, "page": page}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/pages/{page_id}/move")
def api_move_page(request: Request, page_id: str, body: PageMove) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            page = wiki_domain.move_page(
                session,
                ctx_of(user),
                page_id=page_id,
                parent_id=body.parent_id,
                sort_order=body.sort_order,
            )
        return {"ok": True, "page": page}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/pages/{page_id}")
def api_delete_page(request: Request, page_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            result = wiki_domain.delete_page(session, ctx_of(user), page_id=page_id)
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


def register(app, _kit) -> None:
    app.include_router(router)
