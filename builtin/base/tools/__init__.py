"""Base module MCP tools — users / roles / installed apps (modules)."""

from __future__ import annotations

from typing import Any

from modoor.core.errors import AppError
from modoor.runtime.tool import run_tool
from builtin.base import domain as base_domain


def register_adapters() -> None:
    from builtin.base.adapters import ensure_base_adapters

    ensure_base_adapters()


def get_user(user_id: int | None = None, username: str | None = None) -> str:
    """Get a user by id or username."""
    args = {"user_id": user_id, "username": username}

    def _inner(session, ctx, _settings):
        return base_domain.get_user(session, ctx, user_id=user_id, username=username)

    return run_tool("base.get_user", args, _inner, readonly=True)


def list_users(q: str | None = None, limit: int = 50) -> str:
    """List users in the current tenant."""
    args = {"q": q, "limit": limit}

    def _inner(session, ctx, _settings):
        return base_domain.list_users(session, ctx, q=q, limit=limit)

    return run_tool("base.list_users", args, _inner, readonly=True)


def get_role(role_id: str | None = None, code: str | None = None) -> str:
    """Get a role by id or code (includes users/nodes when present)."""
    args = {"role_id": role_id, "code": code}

    def _inner(session, ctx, _settings):
        return base_domain.get_role(session, ctx, role_id=role_id, code=code)

    return run_tool("base.get_role", args, _inner, readonly=True)


def list_roles(q: str | None = None, limit: int = 50) -> str:
    """List roles in the current tenant."""
    args = {"q": q, "limit": limit}

    def _inner(session, ctx, _settings):
        return base_domain.list_roles(session, ctx, q=q, limit=limit)

    return run_tool("base.list_roles", args, _inner, readonly=True)


def list_apps() -> str:
    """List installed apps (on-disk modules) and enabled state for this tenant."""
    from modoor.platform.module_state import list_modules as _list
    from modoor.platform.module_state import sync_discovered_modules

    def _inner(session, ctx, settings):
        sync_discovered_modules(session, ctx.tenant, settings)
        return {"items": _list(session, ctx.tenant, settings=settings)}

    return run_tool("base.list_apps", {}, _inner, readonly=True)


def read_app(app_id: str) -> str:
    """Read one installed app by id (module id, e.g. fleet / wiki / base)."""
    from modoor.platform.module_state import list_modules as _list
    from modoor.platform.module_state import sync_discovered_modules

    args = {"app_id": app_id}

    def _inner(session, ctx, settings):
        mid = (app_id or "").strip()
        if not mid:
            raise AppError("validation_error", "app_id required")
        sync_discovered_modules(session, ctx.tenant, settings)
        items = _list(session, ctx.tenant, settings=settings)
        hit = next((x for x in items if str(x.get("id") or "") == mid), None)
        if hit is None:
            raise AppError("not_found", f"app not found: {app_id}")
        return {"item": hit}

    return run_tool("base.read_app", args, _inner, readonly=True)


def schema(
    model: str,
    using: str = "default",
    scene: str = "SEARCH",
    kind: str = "table",
) -> str:
    """Fetch model schema via engine (fields / filters / default query / digest meta).

    kind:
      - table (default): list/digest view — same as PC SchemaView
      - input: form fields (INSERT / UPDATE / DETAIL); set scene accordingly
    """
    args = {"model": model, "using": using, "scene": scene, "kind": kind}

    def _inner(session, ctx, _settings):
        mid = (model or "").strip()
        if not mid:
            raise AppError("validation_error", "model required")
        from modoor.engine import get_engine

        engine = get_engine()
        body = {
            "model": mid,
            "using": (using or "default").strip() or "default",
            "scene": (scene or "SEARCH").strip() or "SEARCH",
        }
        k = (kind or "table").strip().lower()
        if k == "input":
            return engine.input_schema(session, ctx, body)
        if k not in ("table", ""):
            raise AppError(
                "validation_error",
                f"unknown kind '{kind}'; expected table | input",
            )
        return engine.table_schema(session, ctx, body)

    return run_tool("base.schema", args, _inner, readonly=True)


def search(
    model: str,
    using: str = "default",
    query: dict[str, Any] | None = None,
    page: int = 1,
    size: int = 50,
) -> str:
    """Search / digest a model view — same engine path as PC SchemaView.

    Pass the same ``using`` as the UI tab (e.g. pivot-driver, rpt.site.loadRate)
    to get the rows the user sees. Digest views run group/count/append; plain
    views return detail rows. Optional ``query`` merges over the view defaults.
    """
    args: dict[str, Any] = {
        "model": model,
        "using": using,
        "query": query,
        "page": page,
        "size": size,
    }

    def _inner(session, ctx, _settings):
        mid = (model or "").strip()
        if not mid:
            raise AppError("validation_error", "model required")
        from modoor.engine import get_engine

        try:
            page_n = max(1, int(page or 1))
        except (TypeError, ValueError):
            page_n = 1
        try:
            size_n = max(1, min(int(size or 50), 500))
        except (TypeError, ValueError):
            size_n = 50
        body: dict[str, Any] = {
            "model": mid,
            "using": (using or "default").strip() or "default",
            "scene": "SEARCH",
            "page": page_n,
            "size": size_n,
        }
        if isinstance(query, dict) and query:
            body["query"] = query
        result = get_engine().search(session, ctx, body)
        # Keep agent payload focused (drop bulky refers unless needed).
        return {
            "model": mid,
            "using": body["using"],
            "page": result.get("page"),
            "size": result.get("size"),
            "count": result.get("count"),
            "totals": result.get("totals"),
            "values": result.get("values"),
        }

    return run_tool("base.search", args, _inner, readonly=True)


def register(mcp) -> None:
    register_adapters()
    mcp.tool(name="base.get_user")(get_user)
    mcp.tool(name="base.list_users")(list_users)
    mcp.tool(name="base.get_role")(get_role)
    mcp.tool(name="base.list_roles")(list_roles)
    mcp.tool(name="base.list_apps")(list_apps)
    mcp.tool(name="base.read_app")(read_app)
    mcp.tool(name="base.schema")(schema)
    mcp.tool(name="base.search")(search)
