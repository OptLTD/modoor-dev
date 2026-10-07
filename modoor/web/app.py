"""PC web console shell — auth, registry, health; module routes via ui/web.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from modoor.platform.bootstrap import bootstrap
from modoor.core.db import init_db, session_scope
from modoor.core.errors import AppError
from modoor.engine.api import router as engine_router
from modoor.platform.loader import register_module_web
from modoor.platform import services as service_registry
from modoor.platform.tickets import issue_ticket, verify_ticket
from modoor.core.settings import get_settings
from modoor.web.frontend import register_frontends
from modoor.web.kit import get_kit
from modoor.web.agent_routes import register_agent_routes
from modoor.web.nav import (
    clear_ui_cache,
    get_module_meta,
    registry_catalog,
    resolve_home,
)
from builtin.base import domain as base_domain


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_settings.cache_clear()
    clear_ui_cache()
    init_db()
    bootstrap()
    from modoor.runtime.mcp_http import mcp_http_lifespan
    from modoor.runtime.worker import start_inprocess, stop_inprocess

    start_inprocess()
    try:
        async with mcp_http_lifespan():
            yield
    finally:
        stop_inprocess()


app = FastAPI(title="Modoor Console", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().modoor_session_secret,
    session_cookie="modoor_session",
    same_site="lax",
    https_only=False,
)


def _cors_origins() -> list[str]:
    """Vite module ports from MODOOR_MODULE_URLS (+ localhost aliases)."""
    settings = get_settings()
    origins: set[str] = set()
    raw = getattr(settings, "modoor_webui_module_urls", None) or settings.modoor_module_urls
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        _, url = part.split("=", 1)
        url = url.strip().rstrip("/")
        if url.isdigit():
            url = f"http://127.0.0.1:{url}"
        elif "://" not in url:
            continue
        origins.add(url)
        if "127.0.0.1" in url:
            origins.add(url.replace("127.0.0.1", "localhost"))
        elif "localhost" in url:
            origins.add(url.replace("localhost", "127.0.0.1"))
    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(engine_router)

from modoor.runtime.mcp_http import mount_http_mcp

mount_http_mcp(app)
register_agent_routes(app)

_LOGO_PNG = Path(__file__).resolve().parents[2] / "logo.png"

kit = get_kit()
register_module_web(app, kit)
register_frontends(app)


# ---- Auth / home / health ----

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    next_url = request.query_params.get("next") or ""
    user = kit.current_user(request)
    if user:
        with session_scope() as session:
            mid, href = kit.landing_for_user(session, user, next_url=next_url)
            if mid:
                request.session["active_module"] = mid
            else:
                request.session.pop("active_module", None)
        return RedirectResponse(href, status_code=303)
    return kit.render(
        request,
        "login.html",
        {"username": "admin", "next": next_url, "error": None},
    )


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
):
    try:
        with session_scope() as session:
            user = base_domain.authenticate_user(
                session,
                tenant=kit.tenant(),
                username=username,
                password=password,
                allow_fallback=True,
            )
            request.session["user_id"] = user.id
            request.session["username"] = user.username
            mid, href = kit.landing_for_user(session, user, next_url=next)
            if mid:
                request.session["active_module"] = mid
            else:
                request.session.pop("active_module", None)
    except AppError as exc:
        return kit.render(
            request,
            "login.html",
            {"error": exc.message, "username": username, "next": next},
            status_code=400,
        )
    return RedirectResponse(href, status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = kit.current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    request.session.pop("active_module", None)
    with session_scope() as session:
        apps = kit.workbench_apps(session, user)
        groups = kit.workbench_groups(session, user)
    return kit.render(request, "home.html", {"apps": apps, "groups": groups})


@app.get("/logout")
@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    accept = request.headers.get("accept") or ""
    if "application/json" in accept:
        return {"ok": True}
    return RedirectResponse("/login", status_code=303)


@app.get("/logo.png", include_in_schema=False)
def logo_png():
    if not _LOGO_PNG.is_file():
        raise HTTPException(status_code=404, detail="logo not found")
    return FileResponse(_LOGO_PNG, media_type="image/png")


@app.get("/health")
def health():
    s = kit.settings()
    return {
        "status": "ok",
        "tenant": s.modoor_tenant,
        "database": s.database_url.split("@")[-1]
        if "@" in s.database_url
        else s.database_url,
        "registered_services": len(service_registry.list_services()),
    }


# ---- External apps (Modoor as hub) ----


class AppRegisterIn(BaseModel):
    """Register an external app. ``id`` is both registry key and module id by default."""

    id: str
    entry_url: str
    app_name: str = ""
    health_url: str | None = None
    module_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class HeartbeatIn(BaseModel):
    entry_url: str | None = None
    manifest: dict[str, Any] | None = None
    artifacts: dict[str, Any] | None = None


class ManifestArtifactsIn(BaseModel):
    manifest: dict[str, Any] | None = None
    artifacts: dict[str, Any] | None = None


def _require_api_key(request: Request) -> None:
    auth = request.headers.get("Authorization") or ""
    key = request.headers.get("X-API-Key") or ""
    if auth.lower().startswith("bearer "):
        key = key or auth[7:].strip()
    if key != kit.settings().modoor_api_key:
        raise HTTPException(status_code=401, detail="invalid api key")


def _user_from_ticket(token: str | None):
    payload = verify_ticket(token or "")
    if not payload:
        return None
    with session_scope() as session:
        user = base_domain.load_user(session, payload["user_id"], tenant=payload["tenant"])
        if user is None or not user.active:
            return None
        if user.tenant != kit.tenant():
            return None
        return kit.detach_user(session, user)


def asdict_app(rec) -> dict[str, Any]:
    from dataclasses import asdict

    data = asdict(rec)
    data["id"] = rec.service_id
    return data


def _apps_catalog(request: Request, *, user):
    tenant = int(user.tenant) if user is not None else kit.tenant()
    with session_scope() as session:
        enabled = kit.enabled(session, tenant)
        allowed = None
        if user is not None:
            from modoor.platform.services import list_services

            extra = {
                str(svc.get("module_id") or svc.get("service_id") or "")
                for svc in list_services()
            }
            extra.discard("")
            allowed = base_domain.allowed_modules_for_user(
                session,
                kit.ctx(user),
                user_id=user.id,
                enabled=enabled,
                extra_module_ids=extra,
            )
    return registry_catalog(enabled, user=user, allowed_modules=allowed)


@app.get("/api/apps/catalog")
def api_apps_catalog(request: Request):
    """Catalog for external apps (ticket) and optional session users."""
    ticket = request.headers.get("X-Modoor-Ticket") or request.query_params.get("ticket")
    user = kit.current_user(request) or _user_from_ticket(ticket)
    return _apps_catalog(request, user=user)


@app.get("/api/shell/modules")
def api_shell_modules(request: Request):
    """Shell switcher catalog (session). Same payload as ``/api/apps/catalog``."""
    user = kit.require_user(request)
    return _apps_catalog(request, user=user)


@app.post("/auth/switch")
def switch_tenant_form(request: Request, tenant_id: int = Form(...)):
    user = kit.require_user(request)
    with session_scope() as session:
        switched = base_domain.switch_login_tenant(
            session, base_id=user.base_id, tenant_id=int(tenant_id)
        )
        request.session["user_id"] = switched.id
        mid, href = kit.landing_for_user(session, switched)
        if mid:
            request.session["active_module"] = mid
        else:
            request.session.pop("active_module", None)
    return RedirectResponse(href, status_code=303)


@app.get("/go/{module_id}")
def launch_module(request: Request, module_id: str):
    user = kit.current_user(request)
    if user is None:
        return RedirectResponse(f"/login?next=/go/{module_id}", status_code=303)
    meta = get_module_meta(module_id)
    if not meta:
        raise HTTPException(status_code=404, detail="module not found")

    with session_scope() as session:
        enabled = kit.enabled(session, user.tenant)
        if module_id not in enabled:
            raise HTTPException(status_code=404, detail="module disabled")
        from modoor.platform.services import list_services

        extra = {
            str(svc.get("module_id") or svc.get("service_id") or "")
            for svc in list_services()
        }
        extra.discard("")
        allowed = base_domain.allowed_modules_for_user(
            session,
            kit.ctx(user),
            user_id=user.id,
            enabled=enabled,
            extra_module_ids=extra,
        )
        if allowed is not None and module_id not in allowed:
            raise HTTPException(status_code=403, detail="module not permitted")

    target = resolve_home(module_id, meta)
    if meta.get("kind") == "external" or meta.get("source") == "external":
        if not target or not str(target).startswith("http"):
            raise HTTPException(status_code=503, detail="external app offline")
        ticket = issue_ticket(user_id=user.id, tenant=user.tenant)
        sep = "&" if "?" in target else "?"
        target = f"{target}{sep}modoor_ticket={ticket}"
    request.session["active_module"] = module_id
    return RedirectResponse(target, status_code=303)


@app.get("/api/apps")
def api_apps_list(request: Request):
    _require_api_key(request)
    return {"items": service_registry.list_services()}


@app.get("/api/apps/exports")
def api_apps_exports():
    return service_registry.aggregated_exports()


@app.post("/api/apps")
def api_apps_register(request: Request, body: AppRegisterIn):
    _require_api_key(request)
    app_id = (body.id or "").strip()
    if not app_id:
        raise HTTPException(status_code=400, detail="id is required")
    module_id = (body.module_id or app_id).strip() or app_id
    try:
        rec = service_registry.register_service(
            service_id=app_id,
            module_id=module_id,
            app_name=body.app_name or module_id,
            entry_url=body.entry_url,
            health_url=body.health_url,
            meta=body.meta,
            manifest=body.manifest or None,
            artifacts=body.artifacts or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "app": asdict_app(rec)}


@app.put("/api/apps/{app_id}/manifest")
def api_apps_set_manifest(request: Request, app_id: str, body: ManifestArtifactsIn):
    _require_api_key(request)
    rec = service_registry.set_manifest_artifacts(
        app_id,
        manifest=body.manifest,
        artifacts=body.artifacts,
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="app not registered")
    return {"ok": True, "app": asdict_app(rec)}


@app.post("/api/apps/{app_id}/heartbeat")
def api_apps_heartbeat(request: Request, app_id: str, body: HeartbeatIn):
    _require_api_key(request)
    rec = service_registry.heartbeat(
        app_id,
        entry_url=body.entry_url,
        manifest=body.manifest,
        artifacts=body.artifacts,
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="app not registered")
    return {"ok": True, "app": asdict_app(rec)}


@app.delete("/api/apps/{app_id}")
def api_apps_delete(request: Request, app_id: str):
    _require_api_key(request)
    ok = service_registry.unregister_service(app_id)
    if not ok:
        raise HTTPException(status_code=404, detail="app not registered")
    return {"ok": True}


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "modoor.web.app:app",
        host=settings.modoor_web_host,
        port=settings.modoor_web_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
