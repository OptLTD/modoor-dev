"""PC Shell kit passed to modules/*/ui/web.py register(app, kit)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse

from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.platform.module_state import enabled_module_ids
from modoor.web.nav import (
    detect_module,
    get_module_meta,
    module_menus,
    switcher_items,
)
from builtin.base import domain as base_domain
from builtin.base.domain import SystemUser

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ShellKit:
    """Shared shell helpers for template modules (auth, render, flash, tenant)."""

    def __init__(self, jinja: Jinja2Templates | None = None) -> None:
        self.templates = jinja or templates

    def settings(self):
        return get_settings()

    def tenant_name(self) -> str:
        return self.settings().modoor_tenant

    def tenant(self) -> int:
        """Resolved tenant id (ensures tenant + root team exist)."""
        from builtin.base.domain import ensure_tenant

        s = self.settings()
        with session_scope() as session:
            return int(
                ensure_tenant(
                    session, s.modoor_tenant, tenant_id=s.modoor_tenant_id
                )["tenant"]["id"]
            )

    def current_user(self, request: Request) -> SystemUser | None:
        uid = request.session.get("user_id")
        if uid is None or uid == "":
            return None
        try:
            user_id = int(uid)
        except (TypeError, ValueError):
            request.session.pop("user_id", None)
            return None
        with session_scope() as session:
            user = base_domain.load_user(session, user_id)
            if user is None or not user.active:
                return None
            return self.detach_user(session, user)

    @staticmethod
    def detach_user(session, user: SystemUser) -> SystemUser:
        """Load login-backed fields, then detach so callers can use the object outside the session."""
        _ = (user.username, user.realname, user.current, user.email, user.active)
        if user.login is not None:
            session.expunge(user.login)
        session.expunge(user)
        return user

    def require_user(self, request: Request) -> SystemUser:
        user = self.current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="login required")
        return user

    def ctx(self, user: SystemUser) -> Ctx:
        return Ctx(tenant=user.tenant, user_id=user.id, team_id=user.team_id)

    def enabled(self, session, tenant: int | None = None) -> set[str]:
        return enabled_module_ids(session, tenant if tenant is not None else self.tenant())

    def allowed_modules_for(self, session, user: SystemUser, enabled: set[str] | None = None) -> set[str] | None:
        enabled = enabled if enabled is not None else self.enabled(session, user.tenant)
        from modoor.platform.services import list_services

        extra = {
            str(svc.get("module_id") or svc.get("service_id") or "")
            for svc in list_services()
        }
        extra.discard("")
        return base_domain.allowed_modules_for_user(
            session,
            self.ctx(user),
            user_id=user.id,
            enabled=enabled,
            extra_module_ids=extra,
        )

    def first_usable_module(
        self,
        session,
        user: SystemUser,
        *,
        enabled: set[str] | None = None,
        allowed_modules: set[str] | None = ...,  # type: ignore[assignment]
    ) -> str:
        """First module in shell switcher order that the user may open."""
        enabled = enabled if enabled is not None else self.enabled(session, user.tenant)
        if allowed_modules is ...:
            allowed_modules = self.allowed_modules_for(session, user, enabled)
        items = switcher_items(enabled, allowed_modules=allowed_modules)
        if items:
            return str(items[0]["id"])
        return "base"

    def landing_for_user(
        self,
        session,
        user: SystemUser,
        *,
        next_url: str | None = None,
    ) -> tuple[str | None, str]:
        """Pick (module_id, href) after login.

        Default landing is the workbench at ``/``. Prefer ``next_url`` only when it
        points at an allowed module (deep link); otherwise stay on the workbench.
        """
        from urllib.parse import urlparse

        enabled = self.enabled(session, user.tenant)
        allowed = self.allowed_modules_for(session, user, enabled)

        raw = (next_url or "").strip()
        href = raw
        if raw.startswith("http://") or raw.startswith("https://"):
            path = urlparse(raw).path or "/"
        else:
            path = (raw.split("?", 1)[0] or "/").strip() or "/"
            href = path
        if path in ("/", "/login"):
            return None, "/"
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "go":
            mid = parts[1]
            if mid and (allowed is None or mid in allowed):
                return mid, href
        mid = detect_module(path)
        if mid and (allowed is None or mid in allowed):
            return mid, href
        return None, "/"

    def workbench_apps(
        self,
        session,
        user: SystemUser,
    ) -> list[dict[str, Any]]:
        """Permission-filtered module cards for the `/` workbench."""
        enabled = self.enabled(session, user.tenant)
        allowed = self.allowed_modules_for(session, user, enabled)
        apps: list[dict[str, Any]] = []
        for item in switcher_items(enabled, allowed_modules=allowed):
            i18n = item.get("i18n") or {}
            zh = i18n.get("zh-CN") if isinstance(i18n, dict) else {}
            en = i18n.get("en-US") if isinstance(i18n, dict) else {}
            if not isinstance(zh, dict):
                zh = {}
            if not isinstance(en, dict):
                en = {}
            fallback = item.get("label") or item["id"]
            title_zh = zh.get("app.label") or zh.get("label") or fallback
            title_en = en.get("app.label") or en.get("label") or fallback
            mid = str(item["id"])
            apps.append(
                {
                    "id": mid,
                    "title": title_zh,
                    "title_zh": title_zh,
                    "title_en": title_en,
                    "mark_zh": (title_zh or mid)[:1],
                    "mark_en": (title_en or mid)[:1],
                    "tone": sum(ord(c) for c in mid) % 6,
                    "href": item.get("href") or item.get("path") or f"/go/{item['id']}",
                    "online": item.get("online", True),
                    "origin": item.get("origin") or "addon",
                }
            )
        return apps

    def workbench_groups(self, session, user: SystemUser) -> list[dict[str, Any]]:
        """Workbench cards split into lightapp / builtin / addon."""
        apps = self.workbench_apps(session, user)
        buckets = {"lightapp": [], "builtin": [], "addon": []}
        for app in apps:
            origin = str(app.get("origin") or "addon")
            if origin not in buckets:
                origin = "addon"
            buckets[origin].append(app)
        groups = [
            {"id": "builtin", "cards": buckets["builtin"]},
            {"id": "addon", "cards": buckets["addon"]},
        ]
        if buckets["lightapp"]:
            groups.insert(0, {"id": "lightapp", "cards": buckets["lightapp"]})
        return groups

    def user_initials(self, user: SystemUser | None) -> str:
        if user is None:
            return "?"
        name = (user.realname or user.username or "?").strip()
        parts = [p for p in name.replace("_", " ").split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper()

    def flash(self, request: Request, message: str) -> None:
        request.session["flash"] = message

    def login_redirect(self) -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    def render(
        self,
        request: Request,
        name: str,
        context: dict[str, Any] | None = None,
        status_code: int = 200,
    ):
        ctx = dict(context or {})
        user = self.current_user(request)
        active_tenant = int(user.tenant) if user is not None else self.tenant()
        with session_scope() as session:
            enabled = self.enabled(session, active_tenant)
            tenants: list[dict[str, Any]] = []
            tenant_label = self.tenant_name()
            allowed_modules: set[str] | None = None
            if user is not None:
                tenants = base_domain.list_login_tenants(session, base_id=user.base_id)
                for tn in tenants:
                    if int(tn["id"]) == active_tenant:
                        tenant_label = str(tn["name"])
                        break
                else:
                    row = session.get(base_domain.SystemTenant, active_tenant)
                    if row is not None:
                        tenant_label = row.name
                allowed_modules = self.allowed_modules_for(session, user, enabled)

            current_module = detect_module(request.url.path) or request.session.get(
                "active_module"
            )
            if request.url.path in ("/", ""):
                current_module = None
            elif current_module and current_module not in enabled:
                current_module = None
            if (
                current_module
                and allowed_modules is not None
                and current_module not in allowed_modules
            ):
                current_module = None
            switcher = switcher_items(enabled, allowed_modules=allowed_modules)

        if current_module:
            request.session["active_module"] = current_module
        else:
            request.session.pop("active_module", None)

        def _app_titles(item: dict[str, Any]) -> tuple[str, str]:
            i18n = item.get("i18n") or {}
            zh = i18n.get("zh-CN") if isinstance(i18n, dict) else {}
            en = i18n.get("en-US") if isinstance(i18n, dict) else {}
            if not isinstance(zh, dict):
                zh = {}
            if not isinstance(en, dict):
                en = {}
            fallback = str(item.get("label") or item.get("id") or "")
            return (
                str(zh.get("app.label") or zh.get("label") or fallback),
                str(en.get("app.label") or en.get("label") or fallback),
            )

        switcher_view: list[dict[str, Any]] = []
        for item in switcher:
            zh_title, en_title = _app_titles(item)
            switcher_view.append({**item, "label_zh": zh_title, "label_en": en_title})

        brand_zh, brand_en = "工作台", "Workbench"
        if current_module:
            hit = next((m for m in switcher_view if m["id"] == current_module), None)
            if hit:
                brand_zh, brand_en = hit["label_zh"], hit["label_en"]
            else:
                meta = get_module_meta(current_module) or {}
                zh_title, en_title = _app_titles(meta)
                brand_zh = zh_title or str(meta.get("label") or current_module)
                brand_en = en_title or brand_zh

        menu_view: list[dict[str, Any]] = []
        if current_module:
            meta = get_module_meta(current_module) or {}
            i18n = meta.get("i18n") or {}
            zh_pack = i18n.get("zh-CN") if isinstance(i18n, dict) else {}
            en_pack = i18n.get("en-US") if isinstance(i18n, dict) else {}
            if not isinstance(zh_pack, dict):
                zh_pack = {}
            if not isinstance(en_pack, dict):
                en_pack = {}

            def _localize_menu(item: dict[str, Any]) -> dict[str, Any]:
                mid = str(item.get("id") or "")
                fallback = str(item.get("label") or mid)
                out = {
                    **item,
                    "label_zh": str(zh_pack.get(mid) or fallback),
                    "label_en": str(en_pack.get(mid) or fallback),
                }
                kids = list(item.get("items") or [])
                if kids:
                    out["items"] = [_localize_menu(c) for c in kids]
                return out

            for item in module_menus(current_module):
                menu_view.append(_localize_menu(item))

        ctx.update(
            {
                "request": request,
                "current_user": user,
                "user_initials": self.user_initials(user),
                "tenant": tenant_label,
                "tenant_id": active_tenant,
                "tenants": tenants,
                "flash": request.session.pop("flash", None),
                "enabled_modules": enabled,
                "current_module": current_module,
                "current_module_label": brand_zh,
                "current_module_label_zh": brand_zh,
                "current_module_label_en": brand_en,
                "module_switcher": switcher_view,
                "module_menus": menu_view,
                "inbox_messages": [],
            }
        )
        return self.templates.TemplateResponse(request, name, ctx, status_code=status_code)


_kit: ShellKit | None = None


def get_kit() -> ShellKit:
    global _kit
    if _kit is None:
        _kit = ShellKit()
    return _kit
