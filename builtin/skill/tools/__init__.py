"""Skill MCP tools — query / read / write."""

from __future__ import annotations

from typing import Any

from modoor.core.errors import AppError
from modoor.runtime.tool import run_tool
from builtin.skill import domain as skill_domain


def query(
    q: str | None = None,
    module: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> str:
    """List skills in the tenant catalog (read-only).

    Merges on-disk module skills with tenant DB overrides (DB wins).
    Optional filters: q (id/title/summary), module, source (module|custom|override).
    Use skill.read for full markdown body.
    """
    args: dict[str, Any] = {
        "q": q,
        "module": module,
        "source": source,
        "limit": limit,
    }

    def _inner(session, ctx, _settings):
        result = skill_domain.list_skills(
            session,
            ctx,
            source=(source or "").strip() or None,
            q=q,
            limit=limit,
        )
        mod = (module or "").strip().lower()
        items = result["items"]
        if mod:
            items = [x for x in items if str(x.get("module") or "") == mod]
        return {"items": items, "count": len(items)}

    return run_tool("skill.query", args, _inner, readonly=True)


def read(skill_id: str) -> str:
    """Read one skill by id (module.skill_key), including markdown body."""
    args = {"skill_id": skill_id}

    def _inner(session, ctx, _settings):
        sid = (skill_id or "").strip()
        if not sid:
            raise AppError("validation_error", "skill_id required")
        return {"item": skill_domain.get_skill(session, ctx, skill_id=sid)}

    return run_tool("skill.read", args, _inner, readonly=True)


def write(
    skill_id: str | None = None,
    skill_key: str | None = None,
    module: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    when_to_use: str | None = None,
    content: str | None = None,
    tools: list[str] | None = None,
    boundaries: str | None = None,
) -> str:
    """Create or update a skill (blocked when Agent is read-only).

    - Update: pass skill_id (module.skill_key); base.* is read-only
    - Create custom: pass skill_key + title (module defaults to custom)
    - Override a module skill: pass skill_id of a non-base module skill
    content: markdown body (without frontmatter)
    """
    args: dict[str, Any] = {
        "skill_id": skill_id,
        "skill_key": skill_key,
        "module": module,
        "title": title,
        "summary": summary,
        "when_to_use": when_to_use,
        "content": content,
        "tools": tools,
        "boundaries": boundaries,
    }

    def _inner(session, ctx, _settings):
        sid = (skill_id or "").strip()
        if sid:
            existing = skill_domain.get_skill(session, ctx, skill_id=sid)
            if existing.get("readonly"):
                raise AppError("permission_denied", "base module skills are read-only")
            skill = skill_domain.upsert_skill(
                session,
                ctx,
                skill_id=sid,
                title=(title if title is not None else existing.get("title") or ""),
                summary=summary if summary is not None else (existing.get("summary") or ""),
                when_to_use=when_to_use
                if when_to_use is not None
                else (existing.get("when_to_use") or ""),
                content=content if content is not None else (existing.get("content") or ""),
                tools=list(tools) if tools is not None else list(existing.get("tools") or []),
                confirmations=list(existing.get("confirmations") or []),
                boundaries=boundaries
                if boundaries is not None
                else (existing.get("boundaries") or ""),
            )
            return {"action": "update", "skill": skill}

        key = (skill_key or "").strip()
        if not key:
            raise AppError(
                "validation_error",
                "skill_id required to update, or skill_key+title to create",
            )
        if not (title or "").strip():
            raise AppError("validation_error", "title required to create a skill")
        skill = skill_domain.upsert_skill(
            session,
            ctx,
            module=(module or "").strip() or skill_domain.CUSTOM_MODULE_ID,
            skill_key=key,
            title=title or "",
            summary=summary or "",
            when_to_use=when_to_use or "",
            content=content or "",
            tools=list(tools) if tools is not None else None,
            boundaries=boundaries or "",
        )
        return {"action": "create", "skill": skill}

    return run_tool("skill.write", args, _inner)


def register(mcp) -> None:
    mcp.tool(name="skill.query")(query)
    mcp.tool(name="skill.read")(read)
    mcp.tool(name="skill.write")(write)
