"""App-facing mobile APIs. Session cookie matches the desktop shell."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from inbuilt.base import domain as base_domain
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.notify import notify_channel, send_code
from modoor.core.settings import get_settings, public_module_gate
from modoor.engine.api import (
    LoginBody,
    _bootstrap_tenant_id,
    _ctx,
    _require_user,
    _user_payload,
    api_login,
    api_profile,
)
from modoor.web.acting import acting_role
from modoor.web.kit import get_kit
from modoor.web.login_auth import (
    captcha_destination,
    captcha_echo_enabled,
    issue_captcha,
    verify_captcha,
)
from modoor.web.mount import MOB_MOUNT_PREFIX
from modoor.web.nav import get_ui_catalog

router = APIRouter()


def mobile_root() -> Path:
    """Sibling of the business module root: ``<parent>/mobile``."""
    return Path(get_settings().modoor_modules_root).resolve().parent / "mobile"


def discover_mobile_ids(root: Path | None = None) -> list[str]:
    """Module ids that have a mobile app (dev package.json or built dist)."""
    root = mobile_root() if root is None else root
    if not root.is_dir():
        return []
    found: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        packaged = (child / "package.json").is_file()
        built = (child / "dist" / "index.html").is_file()
        if packaged or built:
            found.append(child.name)
    return found


def _mobile_label(meta: dict[str, Any], mid: str) -> str:
    i18n = meta.get("i18n") or {}
    zh = i18n.get("zh-CN") if isinstance(i18n, dict) else None
    if isinstance(zh, dict):
        title = str(zh.get("app.label") or "").strip()
        if title:
            return title
    return str(meta.get("label") or mid)


def _mobile_open(
    mid: str,
    *,
    enabled: set[str],
    allowed: set[str] | None,
    catalog: dict[str, dict[str, Any]],
) -> bool:
    """A phone app is open when its module or the desktop host it blends into is on."""
    meta = catalog.get(mid) or {}
    host = str(meta.get("blend") or "").strip()
    if mid not in enabled and not (host and host in enabled):
        return False
    if allowed is None:
        return True
    return mid in allowed or bool(host and host in allowed)


def _module_yaml(mid: str) -> dict[str, Any]:
    import yaml

    from modoor.platform.roots import module_dir

    path = module_dir(mid) / "module.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _mobile_pages(mid: str) -> list[dict[str, str]]:
    """Workbench pages from module.yaml ``exports.mobile``. Empty means the app root."""
    data = _module_yaml(mid)
    exports = data.get("exports") or {}
    raw_pages = exports.get("mobile") if isinstance(exports, dict) else None
    if not isinstance(raw_pages, list):
        return []
    pages: list[dict[str, str]] = []
    for page in raw_pages:
        if not isinstance(page, dict):
            continue
        route = str(page.get("path") or "").strip()
        if not route.startswith("/") or route == "/":
            continue
        pid = str(page.get("id") or "").strip() or f"{mid}{route.replace('/', '.')}"
        label = str(page.get("label") or "").strip() or pid
        icon = str(page.get("icon") or "").strip()
        pages.append({"id": pid, "label": label, "path": route, "icon": icon})
    return pages


def _page_href(base: str, mid: str, route: str) -> str:
    root = f"{base}{MOB_MOUNT_PREFIX}/{mid}"
    if not route or route == "/":
        return f"{root}/"
    return f"{root}{route}"


def _page_icon(base: str, mid: str, icon: str) -> str:
    """Configured path under mobile/<module>/public, or an absolute URL."""
    icon = (icon or "").strip()
    if not icon:
        return ""
    if icon.startswith(("http://", "https://")):
        return icon
    if icon.startswith("/"):
        return f"{base}{icon}"
    return f"{base}{MOB_MOUNT_PREFIX}/{mid}/{icon.lstrip('/')}"


def mobile_entries(request: Request) -> list[dict[str, Any]]:
    """Enabled mobile modules, one group per module."""
    user = _require_user(request)
    kit = get_kit()
    role = acting_role(request)
    with session_scope() as session:
        if not role:
            held = base_domain.list_user_roles(session, _ctx(user), user_id=user.id)[
                "roles"
            ]
            if base_domain.holds_superuser(held):
                role = base_domain.SUPERUSER_CODE
        enabled = kit.enabled(session, user.tenant)
        allowed = kit.allowed_modules_for(
            session, user, enabled, active_role=role
        )
    catalog = get_ui_catalog()
    base = public_module_gate(get_settings().modoor_webui_url) or str(request.base_url).rstrip("/")
    groups: list[dict[str, Any]] = []
    for mid in discover_mobile_ids():
        if not _mobile_open(mid, enabled=enabled, allowed=allowed, catalog=catalog):
            continue
        meta = catalog.get(mid) or {}
        name = _mobile_label(meta, mid)
        pages = _mobile_pages(mid) or [
            {"id": mid, "label": name, "path": "/"}
        ]
        groups.append(
            {
                "group": name,
                "intro": str(_module_yaml(mid).get("summary") or "").strip(),
                "fixed": "no",
                "entry": [
                    {
                        "id": page["id"],
                        "label": page["label"],
                        "href": _page_href(base, mid, page["path"]),
                        "icon": _page_icon(base, mid, page.get("icon") or ""),
                    }
                    for page in pages
                ],
            }
        )
    return groups


class MobLoginBody(BaseModel):
    username: str
    password: str = ""
    captcha: str = ""


class CaptchaBody(BaseModel):
    username: str


class DeviceBody(BaseModel):
    device_id: str = ""
    model: str = ""
    brand: str = ""
    system: str = ""
    version: str = ""


def _http_error(exc: AppError, *, status: int = 400) -> HTTPException:
    code = 429 if exc.code == "rate_limited" else status
    return HTTPException(status_code=code, detail=exc.message)


def _open_session(request: Request, user_id: int) -> dict[str, Any]:
    shell = get_kit()
    with session_scope() as session:
        attached = base_domain.load_user(session, int(user_id))
        if attached is None or not attached.active:
            raise HTTPException(status_code=401, detail="login required")
        tenants = base_domain.list_login_tenants(session, base_id=attached.base_id)
        request.session["user_id"] = attached.id
        mid, _href = shell.landing_for_user(
            session, attached, active_role=acting_role(request)
        )
        if mid:
            request.session["active_module"] = mid
        else:
            request.session.pop("active_module", None)
        payload = _user_payload(attached, tenants=tenants)
    return {"ok": True, "user": payload}


@router.post("/api/mob/captcha")
def mob_captcha(request: Request, body: CaptchaBody) -> dict[str, Any]:
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="请输入登录名称")
    try:
        channel = notify_channel()
    except AppError as exc:
        raise _http_error(exc) from exc
    echo = captcha_echo_enabled()
    with session_scope() as session:
        if not base_domain.has_active_login(session, username):
            raise HTTPException(status_code=404, detail="用户不存在")
        if not channel and not echo:
            raise HTTPException(status_code=400, detail="未配置短信或邮件，无法发送验证码")
        try:
            target = captcha_destination(session, username, channel)
        except AppError as exc:
            raise _http_error(exc) from exc
    try:
        code = issue_captcha(request, username)
    except AppError as exc:
        raise _http_error(exc) from exc
    if channel:
        try:
            send_code(channel=channel, target=target, code=code)
        except AppError as exc:
            request.session.pop("login_captcha", None)
            request.session.pop("login_captcha_at", None)
            raise _http_error(exc) from exc
    payload: dict[str, Any] = {"ok": True}
    if echo:
        payload["dev_code"] = code
    return payload


@router.post("/api/mob/login")
def mob_login(request: Request, body: MobLoginBody) -> dict[str, Any]:
    code = body.captcha.strip()
    if code:
        try:
            verify_captcha(request, body.username, code)
            tenant_id = _bootstrap_tenant_id()
            with session_scope() as session:
                user = base_domain.login_user_by_username(
                    session,
                    username=body.username,
                    tenant=tenant_id,
                    allow_fallback=True,
                )
                user_id = int(user.id)
        except AppError as exc:
            status = 401 if exc.code == "permission_denied" else 400
            raise _http_error(exc, status=status) from exc
        return _open_session(request, user_id)
    signed = api_login(request, LoginBody(username=body.username, password=body.password))
    return {"ok": True, "user": signed["user"]}


@router.put("/api/mob/device")
def mob_device(request: Request, body: DeviceBody) -> dict[str, Any]:
    user = _require_user(request)
    now = datetime.now(timezone.utc).isoformat()
    with session_scope() as session:
        row = base_domain.load_user(session, int(user.id))
        if row is None or row.login is None:
            raise HTTPException(status_code=401, detail="login required")
        previous = dict(row.login.device or {})
        same = str(previous.get("device_id") or "") == body.device_id.strip()
        first = previous.get("first_login_at") if same and previous.get("first_login_at") else now
        saved = {
            "device_id": body.device_id.strip(),
            "model": body.model.strip(),
            "brand": body.brand.strip(),
            "system": body.system.strip(),
            "version": body.version.strip(),
            "first_login_at": first,
            "latest_login_at": now,
            "latest_active_at": now,
        }
        row.login.device = saved
    return {"ok": True, "device": saved}


@router.get("/api/mob/profile")
def mob_profile(request: Request) -> dict[str, Any]:
    return api_profile(request)


@router.get("/api/mob/home")
def mob_home(request: Request) -> dict[str, Any]:
    return {"entries": mobile_entries(request)}
