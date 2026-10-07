"""Wiki domain — projects, hierarchical pages, BlockNote JSON body."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def empty_blocks_doc(text: str = "") -> str:
    """Minimal BlockNote document (one paragraph)."""
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text, "styles": {}})
    block = {
        "id": _new_id().replace("-", "")[:16],
        "type": "paragraph",
        "props": {
            "textColor": "default",
            "backgroundColor": "default",
            "textAlignment": "left",
        },
        "content": content,
        "children": [],
    }
    return json.dumps([block])


def markdown_to_blocks_json(raw: str) -> str:
    """Wrap plain/markdown text as BlockNote paragraph blocks (seed helpers)."""
    text = (raw or "").strip()
    if not text:
        return empty_blocks_doc()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return text
    except json.JSONDecodeError:
        pass
    blocks: list[dict[str, Any]] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        blocks.append(
            {
                "id": _new_id().replace("-", "")[:16],
                "type": "paragraph",
                "props": {
                    "textColor": "default",
                    "backgroundColor": "default",
                    "textAlignment": "left",
                },
                "content": [{"type": "text", "text": para, "styles": {}}],
                "children": [],
            }
        )
    return json.dumps(blocks or json.loads(empty_blocks_doc()))


class WikiProject(Base):
    __tablename__ = "wiki_project"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    home_page_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class WikiPage(Base):
    __tablename__ = "wiki_page"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


def _project_to_dict(project: WikiProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "tenant": project.tenant,
        "team_id": project.team_id,
        "name": project.name,
        "description": project.description or "",
        "home_page_id": project.home_page_id,
        "created_by": project.created_by,
        "updated_by": project.updated_by,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _page_to_dict(page: WikiPage, *, include_body: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": page.id,
        "tenant": page.tenant,
        "team_id": page.team_id,
        "project_id": page.project_id,
        "parent_id": page.parent_id,
        "sort_order": page.sort_order,
        "title": page.title,
        "created_by": page.created_by,
        "updated_by": page.updated_by,
        "created_at": page.created_at.isoformat() if page.created_at else None,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }
    if include_body:
        data["body"] = page.body
    return data


def _scope_projects(ctx: Ctx):
    return select(WikiProject).where(WikiProject.tenant == ctx.tenant)


def _scope_pages(ctx: Ctx):
    return select(WikiPage).where(WikiPage.tenant == ctx.tenant)


def _get_project(session: Session, ctx: Ctx, project_id: str) -> WikiProject:
    project = session.get(WikiProject, project_id)
    if project is None or project.tenant != ctx.tenant:
        raise AppError("not_found", "Wiki project not found")
    return project


def _get_page(session: Session, ctx: Ctx, page_id: str) -> WikiPage:
    page = session.get(WikiPage, page_id)
    if page is None or page.tenant != ctx.tenant:
        raise AppError("not_found", "Wiki page not found")
    return page


def create_project(
    session: Session,
    ctx: Ctx,
    *,
    name: str,
    description: str = "",
    home_title: str = "Home",
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise AppError("validation_error", "name is required")
    project_id = _new_id()
    page_id = _new_id()
    project = WikiProject(
        id=project_id,
        tenant=ctx.tenant,
        team_id=ctx.team_id,
        name=name,
        description=(description or "").strip(),
        home_page_id=None,
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    session.add(project)
    session.flush()
    page = WikiPage(
        id=page_id,
        tenant=ctx.tenant,
        team_id=ctx.team_id,
        project_id=project_id,
        parent_id=None,
        sort_order=0,
        title=home_title.strip() or "Home",
        body=empty_blocks_doc(f"Welcome to {name}"),
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    session.add(page)
    session.flush()
    project.home_page_id = page_id
    project.updated_at = _now()
    session.flush()
    return {
        "project": _project_to_dict(project),
        "home_page": _page_to_dict(page),
    }


def update_project(
    session: Session,
    ctx: Ctx,
    *,
    project_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    project = _get_project(session, ctx, project_id)
    if name is None and description is None:
        raise AppError("validation_error", "provide name and/or description")
    if name is not None:
        name = name.strip()
        if not name:
            raise AppError("validation_error", "name cannot be empty")
        project.name = name
    if description is not None:
        project.description = description.strip()
    project.updated_by = ctx.user_id
    project.updated_at = _now()
    session.flush()
    return _project_to_dict(project)


def get_project(session: Session, ctx: Ctx, *, project_id: str) -> dict[str, Any]:
    return _project_to_dict(_get_project(session, ctx, project_id))


def list_projects(session: Session, ctx: Ctx) -> dict[str, Any]:
    rows = list(session.scalars(_scope_projects(ctx).order_by(WikiProject.updated_at.desc())))
    return {"items": [_project_to_dict(p) for p in rows], "count": len(rows)}


def delete_project(session: Session, ctx: Ctx, *, project_id: str) -> dict[str, Any]:
    project = _get_project(session, ctx, project_id)
    payload = _project_to_dict(project)
    pages = list(
        session.scalars(select(WikiPage).where(WikiPage.project_id == project_id))
    )
    for page in pages:
        session.delete(page)
    session.delete(project)
    session.flush()
    return {"deleted": True, "project": payload}


def get_tree(session: Session, ctx: Ctx, *, project_id: str) -> dict[str, Any]:
    _get_project(session, ctx, project_id)
    pages = list(
        session.scalars(
            select(WikiPage)
            .where(WikiPage.tenant == ctx.tenant, WikiPage.project_id == project_id)
            .order_by(WikiPage.sort_order.asc(), WikiPage.created_at.asc())
        )
    )
    by_parent: dict[str | None, list[WikiPage]] = {}
    for page in pages:
        by_parent.setdefault(page.parent_id, []).append(page)

    def build(parent_id: str | None) -> list[dict[str, Any]]:
        nodes = []
        for page in by_parent.get(parent_id, []):
            nodes.append(
                {
                    "id": page.id,
                    "title": page.title,
                    "sort_order": page.sort_order,
                    "parent_id": page.parent_id,
                    "children": build(page.id),
                }
            )
        return nodes

    project = _get_project(session, ctx, project_id)
    return {
        "project_id": project_id,
        "home_page_id": project.home_page_id,
        "tree": build(None),
    }


def create_page(
    session: Session,
    ctx: Ctx,
    *,
    project_id: str,
    title: str,
    body: str | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    _get_project(session, ctx, project_id)
    title = title.strip()
    if not title:
        raise AppError("validation_error", "title is required")
    if parent_id:
        parent = _get_page(session, ctx, parent_id)
        if parent.project_id != project_id:
            raise AppError("validation_error", "parent_id must belong to the same project")

    siblings_q = select(WikiPage).where(WikiPage.project_id == project_id)
    if parent_id is None:
        siblings_q = siblings_q.where(WikiPage.parent_id.is_(None))
    else:
        siblings_q = siblings_q.where(WikiPage.parent_id == parent_id)
    siblings = list(session.scalars(siblings_q))
    sort_order = max((s.sort_order for s in siblings), default=-1) + 1

    raw_body = body if body is not None else empty_blocks_doc()
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise AppError("validation_error", "body must be BlockNote JSON array") from exc
    if not isinstance(parsed, list):
        raise AppError("validation_error", "body must be BlockNote JSON array")

    page = WikiPage(
        id=_new_id(),
        tenant=ctx.tenant,
        team_id=ctx.team_id,
        project_id=project_id,
        parent_id=parent_id,
        sort_order=sort_order,
        title=title,
        body=raw_body,
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    session.add(page)
    session.flush()
    return _page_to_dict(page)


def update_page(
    session: Session,
    ctx: Ctx,
    *,
    page_id: str,
    title: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    page = _get_page(session, ctx, page_id)
    if title is None and body is None:
        raise AppError("validation_error", "provide title and/or body")
    if title is not None:
        title = title.strip()
        if not title:
            raise AppError("validation_error", "title cannot be empty")
        page.title = title
    if body is not None:
        page.body = body
    page.updated_by = ctx.user_id
    page.updated_at = _now()
    session.flush()
    return _page_to_dict(page)


def get_page(session: Session, ctx: Ctx, *, page_id: str) -> dict[str, Any]:
    return _page_to_dict(_get_page(session, ctx, page_id))


def list_pages(
    session: Session,
    ctx: Ctx,
    *,
    project_id: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        raise AppError("validation_error", "limit must be between 1 and 200")
    stmt = _scope_pages(ctx).order_by(WikiPage.updated_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(WikiPage.project_id == project_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(WikiPage.title.ilike(like))
    pages = list(session.scalars(stmt))
    return {
        "items": [_page_to_dict(p, include_body=False) for p in pages],
        "count": len(pages),
    }


def move_page(
    session: Session,
    ctx: Ctx,
    *,
    page_id: str,
    parent_id: str | None = None,
    sort_order: int | None = None,
) -> dict[str, Any]:
    page = _get_page(session, ctx, page_id)
    if parent_id is not None:
        if parent_id == page_id:
            raise AppError("validation_error", "page cannot be its own parent")
        parent = _get_page(session, ctx, parent_id)
        if parent.project_id != page.project_id:
            raise AppError("validation_error", "parent must be in the same project")
        # Prevent cycles
        walk = parent
        while walk.parent_id:
            if walk.parent_id == page_id:
                raise AppError("validation_error", "move would create a cycle")
            walk = _get_page(session, ctx, walk.parent_id)

    project = _get_project(session, ctx, page.project_id)
    if project.home_page_id == page_id and parent_id is not None:
        raise AppError("validation_error", "home page must stay at project root")

    page.parent_id = parent_id
    if sort_order is not None:
        page.sort_order = int(sort_order)
    page.updated_by = ctx.user_id
    page.updated_at = _now()
    session.flush()
    return _page_to_dict(page, include_body=False)


def delete_page(session: Session, ctx: Ctx, *, page_id: str) -> dict[str, Any]:
    page = _get_page(session, ctx, page_id)
    project = _get_project(session, ctx, page.project_id)
    if project.home_page_id == page_id:
        raise AppError("validation_error", "cannot delete project home page")

    # Re-parent children to deleted page's parent
    children = list(
        session.scalars(select(WikiPage).where(WikiPage.parent_id == page_id))
    )
    for child in children:
        child.parent_id = page.parent_id

    payload = _page_to_dict(page, include_body=False)
    session.delete(page)
    session.flush()
    return {"deleted": True, "page": payload}
