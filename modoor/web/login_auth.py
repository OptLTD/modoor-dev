"""Login captcha and remember-me cookies for the console sign-in page."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import Response

from builtin.base import domain as base_domain
from builtin.base.domain import SystemUser
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import get_settings

_STATIC = Path(__file__).resolve().parent / "static" / "login"
LOGIN_ASSETS: dict[str, tuple[Path, str]] = {
    "login-bg.jpeg": (_STATIC / "login-bg.jpeg", "image/jpeg"),
    "login-view.png": (_STATIC / "login-view.png", "image/png"),
    "login-view.webm": (_STATIC / "login-view.webm", "video/webm"),
}

REMEMBER_COOKIE = "modoor_remember"
LOGIN_NAME_COOKIE = "modoor_login_name"
LOGIN_REMEMBER_FLAG = "modoor_login_remember"
REMEMBER_MAX_AGE = 30 * 24 * 60 * 60
_REMEMBER_SALT = "modoor-remember-login"
_DEV_SESSION_SECRET = "dev-session-secret-change-me"

CAPTCHA_TTL = 300
CAPTCHA_COOLDOWN = 60
CAPTCHA_MAX_TRIES = 5


def captcha_echo_enabled() -> bool:
    """Show the code on the page when no SMS/email sender is configured.

    Explicit ``MODOOR_CAPTCHA_ECHO`` wins. Otherwise echo only while the
    session secret is still the built-in dev default.
    """
    settings = get_settings()
    if settings.modoor_captcha_echo is not None:
        return bool(settings.modoor_captcha_echo)
    return settings.modoor_session_secret == _DEV_SESSION_SECRET


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().modoor_session_secret, salt=_REMEMBER_SALT)


def _password_stamp(user: SystemUser) -> str:
    secret = ""
    if user.login is not None and user.login.password:
        secret = user.login.password
    return hashlib.sha256(secret.encode()).hexdigest()[:16]


def issue_remember_token(user: SystemUser) -> str:
    return _serializer().dumps({"user_id": int(user.id), "stamp": _password_stamp(user)})


def _read_remember(token: str) -> dict | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=REMEMBER_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    user_id = data.get("user_id")
    stamp = data.get("stamp")
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        return {"user_id": int(user_id), "stamp": stamp}
    except (TypeError, ValueError):
        return None


def restore_remembered_session(request: Request) -> int | None:
    """Fill an empty session from the remember cookie. Returns the user id."""
    existing = request.session.get("user_id")
    if existing not in (None, ""):
        try:
            return int(existing)
        except (TypeError, ValueError):
            return None
    if request.method == "POST" and request.url.path == "/login":
        return None
    token = request.cookies.get(REMEMBER_COOKIE) or ""
    payload = _read_remember(token)
    if payload is None:
        if token:
            request.scope["modoor_clear_remember"] = True
        return None
    with session_scope() as session:
        user = base_domain.load_user(session, payload["user_id"])
        if user is None or not user.active:
            request.scope["modoor_clear_remember"] = True
            return None
        current = _password_stamp(user)
        stamp = payload["stamp"]
        if len(stamp) != len(current) or not hmac.compare_digest(current, stamp):
            request.scope["modoor_clear_remember"] = True
            return None
        username = user.username
        user_id = int(user.id)
    request.session["user_id"] = user_id
    request.session["username"] = username
    return user_id


def apply_login_cookies(
    response: Response,
    *,
    username: str,
    remember: bool,
    token: str | None,
) -> None:
    response.set_cookie(
        LOGIN_NAME_COOKIE,
        (username or "")[:128],
        max_age=REMEMBER_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
    )
    if remember and token:
        response.set_cookie(
            REMEMBER_COOKIE,
            token,
            max_age=REMEMBER_MAX_AGE,
            path="/",
            httponly=True,
            samesite="lax",
        )
        response.set_cookie(
            LOGIN_REMEMBER_FLAG,
            "1",
            max_age=REMEMBER_MAX_AGE,
            path="/",
            httponly=True,
            samesite="lax",
        )
        return
    response.delete_cookie(REMEMBER_COOKIE, path="/")
    response.delete_cookie(LOGIN_REMEMBER_FLAG, path="/")


def _captcha_digest(code: str) -> str:
    secret = get_settings().modoor_session_secret.encode()
    return hmac.new(secret, code.encode(), hashlib.sha256).hexdigest()


def captcha_destination(session, username: str, channel: str) -> str:
    """Address for this channel. Mock only needs the login name."""
    name = (channel or "").strip().lower()
    account = (username or "").strip()
    if name in {"", "mock"}:
        return account
    user = base_domain.login_user_by_username(
        session,
        username=account,
        tenant=get_settings().modoor_tenant_id,
        allow_fallback=True,
    )
    if name == "smtp":
        email = (user.email or "").strip()
        if not email and "@" in account:
            email = account
        if not email:
            raise AppError("validation_error", "该账号未绑定邮箱")
        return email
    if name == "aliyun-sms":
        phone = _sms_phone(user.phone or "") or _sms_phone(account)
        if not phone:
            raise AppError("validation_error", "该账号未绑定手机号")
        return phone
    raise AppError("validation_error", f"不支持的通知通道: {name}")


def _sms_phone(raw: str) -> str:
    text = re.sub(r"[\s\-]", "", (raw or "").strip())
    if text.startswith("+86"):
        text = text[3:]
    elif text.startswith("86") and len(text) == 13:
        text = text[2:]
    if text.isdigit() and 5 <= len(text) <= 20:
        return text
    return ""


def issue_captcha(request: Request, username: str) -> str:
    now = time.time()
    sent = float(request.session.get("login_captcha_at") or 0)
    if sent and now - sent < CAPTCHA_COOLDOWN:
        wait = max(1, int(CAPTCHA_COOLDOWN - (now - sent) + 0.999))
        raise AppError("rate_limited", f"请 {wait} 秒后再试", {"retry_after": wait})
    code = f"{secrets.randbelow(1_000_000):06d}"
    request.session["login_captcha"] = {
        "username": username.strip().lower(),
        "digest": _captcha_digest(code),
        "exp": now + CAPTCHA_TTL,
        "tries": 0,
    }
    request.session["login_captcha_at"] = now
    return code


def verify_captcha(request: Request, username: str, code: str) -> None:
    bag = request.session.get("login_captcha")
    if not isinstance(bag, dict):
        raise AppError("validation_error", "请先获取验证码")
    if float(bag.get("exp") or 0) < time.time():
        request.session.pop("login_captcha", None)
        raise AppError("validation_error", "验证码已过期，请重新获取")
    if str(bag.get("username") or "") != username.strip().lower():
        raise AppError("validation_error", "验证码错误")
    submitted = (code or "").strip()
    digest = str(bag.get("digest") or "")
    got = _captcha_digest(submitted)
    if not digest or len(digest) != len(got) or not hmac.compare_digest(digest, got):
        tries = int(bag.get("tries") or 0) + 1
        if tries >= CAPTCHA_MAX_TRIES:
            request.session.pop("login_captcha", None)
            raise AppError("validation_error", "验证码错误次数过多，请重新获取")
        bag = dict(bag)
        bag["tries"] = tries
        request.session["login_captcha"] = bag
        raise AppError("validation_error", "验证码错误")
    request.session.pop("login_captcha", None)


def _clear_cookie(name: str) -> bytes:
    return f"{name}=; Path=/; Max-Age=0; HttpOnly; SameSite=lax".encode()


def _browser_session_cookie(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    rewritten: list[tuple[bytes, bytes]] = []
    for key, value in headers:
        if key.lower() == b"set-cookie" and value.startswith(b"modoor_session="):
            parts = [part.strip() for part in value.decode().split(";")]
            parts = [
                part
                for part in parts
                if not part.lower().startswith("max-age=")
                and not part.lower().startswith("expires=")
            ]
            value = "; ".join(parts).encode()
        rewritten.append((key, value))
    return rewritten


class SessionPersistMiddleware:
    """Turn the session cookie into a browser session when 记住我 is off."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                if scope.get("modoor_session_persist") is False:
                    headers = _browser_session_cookie(headers)
                if scope.get("modoor_clear_remember"):
                    headers.append((b"set-cookie", _clear_cookie(REMEMBER_COOKIE)))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
