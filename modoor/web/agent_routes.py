"""Public Agent pack under ``/agent`` — readme + skills for hosts (Codex / WorkBuddy / Cursor).

Skills are installed **before** MCP. MCP is tools only (no skill:// resources).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from builtin.skill import domain as skill_domain

router = APIRouter(tags=["agent"])

# Product name for agent-facing docs / skills (EN id + ZH brand).
PRODUCT = "modoor(木牍)"


def _base_url(request: Request | None = None) -> str:
    settings = get_settings()
    configured = str(settings.modoor_webui_url or "").rstrip("/")
    if configured:
        return configured
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8765"


def _exported_skill_ids() -> set[str]:
    """Skill ids listed in module.yaml exports.skills (module-exported only)."""
    from modoor.platform.roots import module_pkg_roots
    import yaml

    allowed: set[str] = set()
    for _pkg, root in module_pkg_roots():
        if not root.is_dir():
            continue
        for mf in sorted(root.glob("*/module.yaml")):
            try:
                data = yaml.safe_load(mf.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                continue
            for sid in (data.get("exports") or {}).get("skills") or []:
                allowed.add(str(sid).strip())
    return allowed


def _skill_public_item(raw: dict[str, Any], *, base: str) -> dict[str, Any]:
    sid = str(raw.get("id") or "")
    return {
        "id": sid,
        "title": raw.get("title") or sid,
        "summary": raw.get("summary") or "",
        "module": raw.get("module") or "",
        "when_to_use": raw.get("when_to_use") or "",
        "tools": list(raw.get("tools") or []),
        "url": f"{base}/agent/skills/{sid}",
    }


def _agent_tenant_ctx():
    """Bootstrap tenant ctx for public /agent skill pack (DB overrides)."""
    from modoor.core.ctx import Ctx
    from builtin.base.domain import ensure_tenant

    settings = get_settings()
    with session_scope() as session:
        tenant = int(
            ensure_tenant(
                session, settings.modoor_tenant, tenant_id=settings.modoor_tenant_id
            )["tenant"]["id"]
        )
    return Ctx(tenant=tenant, user_id=0, team_id=0)


def list_agent_skills(*, base: str, q: str | None = None) -> list[dict[str, Any]]:
    allowed = _exported_skill_ids()
    items: list[dict[str, Any]] = []
    ctx = _agent_tenant_ctx()
    with session_scope() as session:
        merged = skill_domain.list_skills(session, ctx, q=q, limit=500)
        for raw in merged.get("items") or []:
            sid = str(raw.get("id") or "")
            if allowed and sid not in allowed:
                continue
            # Agent pack only ships module-exported ids (incl. tenant overrides).
            if str(raw.get("module") or "") == skill_domain.CUSTOM_MODULE_ID:
                continue
            if raw.get("disabled"):
                continue
            items.append(_skill_public_item(raw, base=base))
    items.sort(key=lambda x: x["id"])
    return items


def _inject_product_heading(markdown: str, *, title: str) -> str:
    """Ensure skill markdown carries modoor(木牍) branding after frontmatter."""
    brand = f"# {PRODUCT} system usage — {title}\n\n"
    text = markdown or ""
    if text.startswith("---"):
        close = text.find("\n---", 3)
        if close != -1:
            end = close + len("\n---")
            rest = text[end:].lstrip("\n")
            if rest.startswith(f"# {PRODUCT}"):
                return text
            return text[:end] + "\n\n" + brand + rest
    if text.startswith(f"# {PRODUCT}"):
        return text
    return brand + text


def build_agent_readme(*, base: str) -> str:
    mcp = f"{base}/mcp"
    skills = list_agent_skills(base=base)
    lines = [
        f"# {PRODUCT} system usage introduction",
        "",
        "Install **skills first**, then connect **MCP** (tools). Do not invent business data.",
        "",
        "## 1. Skills",
        "Fetch each URL below and install it as a skill / instruction in your host "
        "(Codex, WorkBuddy, Cursor, …).",
        "",
    ]
    if not skills:
        lines.append("_No exported skills found._")
    else:
        for s in skills:
            summary = (s.get("summary") or "").strip().replace("\n", " ")
            lines.append(f"- `{s['id']}` — {s['title']}: {summary}")
            lines.append(f"  {s['url']}")
    lines += [
        "",
        "## 2. MCP (tools)",
        f"Streamable HTTP MCP URL: `{mcp}`",
        "",
        "Config example:",
        "```json",
        "{",
        '  "mcpServers": {',
        '    "modoor": {',
        f'      "url": "{mcp}"',
        "    }",
        "  }",
        "}",
        "```",
        "",
        "Auth: browser OAuth (`/auth`) when no key; or `Authorization: Bearer <agent_key>`.",
        "Default is read-only; writes need explicit consent / non-readonly token.",
        "",
        "## 3. How to work",
        "1. Read the skills that match the user task.",
        "2. Call **only** MCP tools listed in those skills.",
        "3. Prefer query/read/aggregate tools; mutate only when allowed.",
        "",
        f"Skill index JSON: `{base}/agent/skills`",
        f"This readme: `{base}/agent/readme`",
    ]
    return "\n".join(lines) + "\n"


def agent_brief_for_clipboard(*, base: str) -> str:
    """Short paste target for Codex / WorkBuddy."""
    return (
        f"请按 {PRODUCT} Agent 说明安装：{base}/agent/readme\n"
        f"- 先安装其中列出的每个 Skill URL。\n"
        f"- 再连接 MCP：{base}/mcp，且仅调用 Skill 中声明的 tools。\n"
    )


@router.get("/agent")
def agent_root() -> RedirectResponse:
    return RedirectResponse("/agent/readme", status_code=307)


@router.get("/agent/readme")
def agent_readme(request: Request) -> Response:
    base = _base_url(request)
    body = build_agent_readme(base=base)
    return Response(body, media_type="text/markdown; charset=utf-8")


@router.get("/agent/brief")
def agent_brief(request: Request) -> PlainTextResponse:
    """One-liner pack for copy-paste into agent chats."""
    return PlainTextResponse(agent_brief_for_clipboard(base=_base_url(request)))


@router.get("/agent/skills")
def agent_skills_list(request: Request, q: str | None = None) -> dict[str, Any]:
    base = _base_url(request)
    return {"base": base, "mcp_url": f"{base}/mcp", "items": list_agent_skills(base=base, q=q)}


@router.get("/agent/skills/{skill_id:path}")
def agent_skill_get(request: Request, skill_id: str) -> Response:
    sid = (skill_id or "").strip().rstrip("/")
    if not sid:
        raise HTTPException(status_code=404, detail="skill not found")
    try:
        ctx = _agent_tenant_ctx()
        with session_scope() as session:
            skill = skill_domain.get_skill(session, ctx, skill_id=sid)
    except Exception as exc:  # noqa: BLE001
        from modoor.core.errors import AppError

        if isinstance(exc, AppError) and exc.code == "not_found":
            raise HTTPException(status_code=404, detail=exc.message) from exc
        if isinstance(exc, AppError) and exc.code == "validation_error":
            raise HTTPException(status_code=400, detail=exc.message) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    allowed = _exported_skill_ids()
    if allowed and skill.get("id") not in allowed:
        raise HTTPException(status_code=404, detail="skill not exported")
    if str(skill.get("module") or "") == skill_domain.CUSTOM_MODULE_ID:
        raise HTTPException(status_code=404, detail="skill not exported")

    md = str(skill.get("markdown") or skill.get("content") or "")
    title = str(skill.get("title") or skill.get("id") or "skill")
    body = _inject_product_heading(md, title=title)
    return Response(body, media_type="text/markdown; charset=utf-8")


def register_agent_routes(app: Any) -> None:
    app.include_router(router)
