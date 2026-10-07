"""Wiki MCP tools — query / read / write."""

from __future__ import annotations

from typing import Any

from modoor.core.errors import AppError
from modoor.runtime.tool import run_tool
from builtin.wiki import domain as wiki_domain

_QUERY_RESOURCES = ("projects", "pages")


def query(
    resource: str,
    project_id: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> str:
    """List wiki projects or pages (read-only).

    resource: projects | pages
      - projects: list projects
      - pages: list pages (optional project_id, q)
    Use wiki.read for a single page body.
    """
    res = (resource or "").strip().lower()
    args: dict[str, Any] = {
        "resource": res,
        "project_id": project_id,
        "q": q,
        "limit": limit,
    }

    def _inner(session, ctx, _settings):
        if res == "projects":
            return {"resource": res, "items": wiki_domain.list_projects(session, ctx)}
        if res == "pages":
            return {
                "resource": res,
                "items": wiki_domain.list_pages(
                    session, ctx, project_id=project_id, q=q, limit=limit
                ),
            }
        raise AppError(
            "validation_error",
            f"unknown resource '{resource}'; expected one of: {', '.join(_QUERY_RESOURCES)}",
        )

    return run_tool("wiki.query", args, _inner, readonly=True)


def read(page_id: str) -> str:
    """Read one wiki page by id (includes BlockNote body)."""
    args = {"page_id": page_id}

    def _inner(session, ctx, _settings):
        if not (page_id or "").strip():
            raise AppError("validation_error", "page_id required")
        return {"item": wiki_domain.get_page(session, ctx, page_id=page_id)}

    return run_tool("wiki.read", args, _inner, readonly=True)


def write(
    page_id: str | None = None,
    project_id: str | None = None,
    title: str | None = None,
    body: str | None = None,
    parent_id: str | None = None,
) -> str:
    """Create or update a wiki page (blocked when Agent is read-only).

    - Update: pass page_id (+ optional title / body)
    - Create: pass project_id + title (+ optional body, parent_id)
    body: BlockNote JSON array, or plain/markdown text (auto-wrapped).
    """
    args: dict[str, Any] = {
        "page_id": page_id,
        "project_id": project_id,
        "title": title,
        "body": body,
        "parent_id": parent_id,
    }

    def _inner(session, ctx, _settings):
        body_json = (
            wiki_domain.markdown_to_blocks_json(body) if body is not None else None
        )
        pid = (page_id or "").strip()
        if pid:
            page = wiki_domain.update_page(
                session,
                ctx,
                page_id=pid,
                title=title,
                body=body_json,
            )
            return {"action": "update", "page": page}

        proj = (project_id or "").strip()
        if not proj:
            raise AppError(
                "validation_error",
                "project_id required to create a page (or pass page_id to update)",
            )
        if not (title or "").strip():
            raise AppError("validation_error", "title required to create a page")
        page = wiki_domain.create_page(
            session,
            ctx,
            project_id=proj,
            title=title or "",
            body=body_json,
            parent_id=(parent_id or "").strip() or None,
        )
        return {"action": "create", "page": page}

    return run_tool("wiki.write", args, _inner)


def register(mcp) -> None:
    mcp.tool(name="wiki.query")(query)
    mcp.tool(name="wiki.read")(read)
    mcp.tool(name="wiki.write")(write)
