"""HTTP: /api/record/* + /api/auth/* for Vue shell."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import get_settings
from modoor.engine.service import get_engine
from builtin.base import domain as base_domain
from builtin.base.domain import SystemUser

router = APIRouter()


def _bootstrap_tenant_id() -> int:
    from builtin.base.domain import ensure_tenant

    with session_scope() as session:
        s = get_settings()
        return int(
            ensure_tenant(session, s.modoor_tenant, tenant_id=s.modoor_tenant_id)[
                "tenant"
            ]["id"]
        )


def _user_payload(
    user: SystemUser, *, tenants: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": user.id,
        "uukey": user.uukey,
        "username": user.username,
        "realname": user.realname,
        "tenant": user.tenant,
        "current": user.current,
        "base_id": user.base_id,
    }
    if tenants is not None:
        payload["tenants"] = tenants
    return payload


def _user_from_session(request: Request) -> SystemUser | None:
    uid = request.session.get("user_id")
    if uid is None or uid == "":
        return None
    try:
        user_id = int(uid)
    except (TypeError, ValueError):
        request.session.pop("user_id", None)
        return None
    with session_scope() as session:
        # By user id only — membership row carries tenant (supports switch).
        user = base_domain.load_user(session, user_id)
        if user is None or not user.active:
            return None
        _ = (user.username, user.realname, user.current)
        if user.login is not None:
            session.expunge(user.login)
        session.expunge(user)
        return user


def _require_user(request: Request) -> SystemUser:
    user = _user_from_session(request)
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    return user


def _ctx(user: SystemUser) -> Ctx:
    return Ctx(tenant=user.tenant, user_id=user.id, team_id=user.team_id)


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, AppError):
        code = 404 if exc.code == "not_found" else 400
        return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, KeyError):
        return HTTPException(status_code=400, detail={"code": "not_found", "message": str(exc)})
    return HTTPException(status_code=500, detail={"code": "internal", "message": str(exc)})


class LoginBody(BaseModel):
    username: str
    password: str


class SwitchTenantBody(BaseModel):
    tenant_id: int


@router.post("/api/auth/login")
def api_login(request: Request, body: LoginBody) -> dict[str, Any]:
    try:
        from modoor.web.kit import get_kit

        shell = get_kit()
        with session_scope() as session:
            user = base_domain.authenticate_user(
                session,
                username=body.username,
                password=body.password,
                tenant=_bootstrap_tenant_id(),
                allow_fallback=True,
            )
            tenants = base_domain.list_login_tenants(session, base_id=user.base_id)
            request.session["user_id"] = user.id
            mid, href = shell.landing_for_user(session, user)
            if mid:
                request.session["active_module"] = mid
            else:
                request.session.pop("active_module", None)
            return {
                "ok": True,
                "user": _user_payload(user, tenants=tenants),
                "module": mid,
                "home": href,
            }
    except AppError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc


@router.get("/api/auth/profile")
def api_profile(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    with session_scope() as session:
        row = base_domain.load_user(session, int(user.id))
        if row is None or not row.active:
            raise HTTPException(status_code=401, detail="login required")
        tenants = base_domain.list_login_tenants(session, base_id=row.base_id)
        return {"user": _user_payload(row, tenants=tenants)}


@router.get("/api/auth/agent-connect")
def api_agent_connect(request: Request) -> dict[str, Any]:
    """HTTP MCP endpoint + agent token; also advertise OAuth (browser) connect."""
    user = _require_user(request)
    settings = get_settings()
    with session_scope() as session:
        row = base_domain.load_user(session, int(user.id))
        if row is None or not row.active:
            raise HTTPException(status_code=401, detail="login required")
        tok = base_domain.ensure_agent_token(session, row)
        base = str(settings.modoor_webui_url or "").rstrip("/")
        mcp_url = f"{base}/mcp"
        auth_url = f"{base}/auth"
        oauth_issuer = base
        key = str(tok.token)
        readonly = tok.is_readonly()
        return {
            "mcp_url": mcp_url,
            "auth_url": auth_url,
            "oauth_issuer": oauth_issuer,
            "agent_readme": f"{base}/agent/readme",
            "agent_brief": f"{base}/agent/brief",
            "agent_skills": f"{base}/agent/skills",
            "agent_key": key,
            "agent_readonly": readonly,
            "token_kind": tok.kind,
            "tenant": row.tenant,
            "user_id": row.id,
            "header": "Authorization: Bearer <agent_key>",
            "alt_header": "X-Agent-Key: <agent_key>",
            "hint": (
                "复制 /agent/brief 给 Codex/WorkBuddy；完整包见 /agent/readme（先 Skill 再 MCP）。"
            ),
            "snippet": {
                "mcpServers": {
                    "modoor": {
                        "url": mcp_url,
                    }
                }
            },
            "snippet_with_key": {
                "mcpServers": {
                    "modoor": {
                        "url": mcp_url,
                        "headers": {"Authorization": f"Bearer {key}"},
                    }
                }
            },
        }


class AgentReadonlyBody(BaseModel):
    readonly: bool = True


@router.post("/api/auth/agent-readonly")
def api_agent_readonly(request: Request, body: AgentReadonlyBody) -> dict[str, Any]:
    """Set read-only on this user's agent token in base_token (default True)."""
    user = _require_user(request)
    with session_scope() as session:
        row = base_domain.load_user(session, int(user.id))
        if row is None or not row.active:
            raise HTTPException(status_code=401, detail="login required")
        flag = base_domain.set_agent_readonly(session, row, bool(body.readonly))
        return {"ok": True, "agent_readonly": flag}


@router.post("/api/auth/agent-key/rotate")
def api_agent_key_rotate(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    with session_scope() as session:
        row = base_domain.load_user(session, int(user.id))
        if row is None or not row.active:
            raise HTTPException(status_code=401, detail="login required")
        key = base_domain.rotate_agent_key(session, row)
        tok = base_domain.get_agent_token(session, row)
        return {
            "ok": True,
            "agent_key": key,
            "agent_readonly": tok.is_readonly() if tok else True,
        }


@router.post("/api/auth/switch")
def api_switch(request: Request, body: SwitchTenantBody) -> dict[str, Any]:
    user = _require_user(request)
    try:
        from modoor.web.kit import get_kit

        shell = get_kit()
        with session_scope() as session:
            row = base_domain.load_user(session, int(user.id))
            if row is None or not row.active:
                raise HTTPException(status_code=401, detail="login required")
            switched = base_domain.switch_login_tenant(
                session, base_id=row.base_id, tenant_id=int(body.tenant_id)
            )
            tenants = base_domain.list_login_tenants(session, base_id=switched.base_id)
            request.session["user_id"] = switched.id
            mid, href = shell.landing_for_user(session, switched)
            if mid:
                request.session["active_module"] = mid
            else:
                request.session.pop("active_module", None)
            return {
                "ok": True,
                "user": _user_payload(switched, tenants=tenants),
                "module": mid,
                "home": href,
            }
    except AppError as exc:
        raise _err(exc) from exc


@router.post("/api/auth/logout")
def api_logout(request: Request) -> dict[str, Any]:
    request.session.clear()
    return {"ok": True}

@router.post("/api/record/schema")
def api_schema(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    try:
        with session_scope() as session:
            return get_engine().table_schema(session, _ctx(user), body)
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/input")
def api_input(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    try:
        with session_scope() as session:
            return get_engine().input_schema(session, _ctx(user), body)
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/autofill")
def api_autofill(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    try:
        with session_scope() as session:
            return get_engine().autofill(session, _ctx(user), body)
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/search")
def api_search(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    try:
        with session_scope() as session:
            return get_engine().search(session, _ctx(user), body)
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/oplogs")
def api_record_oplogs(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    """List modification history for one record (base.oplog by code)."""
    user = _require_user(request)
    model = str(body.get("model") or "").strip()
    code = str(body.get("uukey") or body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="uukey required")
    try:
        limit = int(body.get("limit") or 200)
    except (TypeError, ValueError):
        limit = 200
    try:
        with session_scope() as session:
            items = base_domain.list_record_oplogs(
                session,
                _ctx(user),
                code=code,
                model=model or None,
                limit=limit,
            )
            if not items:
                from modoor.engine.registry import load_sample_oplogs

                items = load_sample_oplogs(model, code, limit)
            return {"items": items, "count": len(items)}
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/upsert")
def api_upsert(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    try:
        with session_scope() as session:
            return get_engine().upsert(session, _ctx(user), body)
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/alloc")
def api_alloc(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    try:
        with session_scope() as session:
            return get_engine().alloc_serials(session, _ctx(user), body)
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc


@router.post("/api/record/delete")
def api_delete(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    user = _require_user(request)
    model = str(body.get("model") or "").strip()
    keys = body.get("keys") or []
    if not model or not isinstance(keys, list):
        raise HTTPException(status_code=400, detail="model and keys required")
    try:
        with session_scope() as session:
            return get_engine().delete(session, _ctx(user), model=model, keys=[str(k) for k in keys])
    except Exception as exc:  # noqa: BLE001
        raise _err(exc) from exc
