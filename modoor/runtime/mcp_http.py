"""Mount Streamable HTTP MCP on the FastAPI app.

Auth: ``base_token`` agent key **or** OAuth access token from ``/auth``.
Unauthenticated requests get 401 + ``WWW-Authenticate`` pointing at protected-resource metadata.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.ctx import Ctx
from modoor.runtime.auth import bind_request_ctx, reset_request_ctx, resolve_ctx_from_agent_key
from modoor.runtime.mcp_oauth import (
    get_oauth_provider,
    mount_mcp_oauth,
    resource_metadata_url,
)
from modoor.runtime.mcp_server import ensure_tools_registered, mcp
from builtin.base import domain as base_domain

logger = logging.getLogger(__name__)

_mcp_http_ready = False


def _extract_bearer(scope: Scope) -> str:
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in (scope.get("headers") or [])
    }
    auth = (headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (headers.get("x-agent-key") or "").strip()


def _www_authenticate() -> str:
    meta = resource_metadata_url()
    return (
        f'Bearer FAKESECRET_k4l5m6n7o8p9q0r1s2t3="Authentication required", '
        f'resource_metadata="{meta}"'
    )


async def _resolve_ctx_from_bearer(key: str) -> Ctx:
    """Accept long-lived agent_key or short-lived OAuth access token."""
    try:
        return resolve_ctx_from_agent_key(key)
    except AppError:
        pass

    access = await get_oauth_provider().load_access_token(key)
    if access is None or not access.subject:
        raise AppError(code="permission_denied", message="Invalid or expired token")

    try:
        user_id = int(access.subject)
    except (TypeError, ValueError) as exc:
        raise AppError(code="permission_denied", message="Invalid token subject") from exc

    readonly = True
    if access.claims and "readonly" in access.claims:
        readonly = bool(access.claims["readonly"])

    with session_scope() as session:
        user = base_domain.load_user(session, user_id)
        if user is None or not user.active:
            raise AppError(code="permission_denied", message="User inactive or missing")
        return Ctx(
            tenant=user.tenant,
            user_id=user.id,
            team_id=user.team_id,
            agent_readonly=readonly,
        )


class McpAuthASGIMiddleware:
    """Require Bearer / X-Agent-Key (agent token or OAuth access token)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        key = _extract_bearer(scope)
        if not key:
            response = JSONResponse(
                {
                    "error": "invalid_token",
                    "error_description": "Authorization Bearer or X-Agent-Key required",
                },
                status_code=401,
                headers={"WWW-Authenticate": _www_authenticate()},
            )
            await response(scope, receive, send)
            return
        try:
            ctx = await _resolve_ctx_from_bearer(key)
        except AppError as exc:
            response = JSONResponse(
                {"error": "invalid_token", "error_description": exc.message},
                status_code=401,
                headers={"WWW-Authenticate": _www_authenticate()},
            )
            await response(scope, receive, send)
            return
        token = bind_request_ctx(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_request_ctx(token)


def build_http_mcp_app() -> ASGIApp:
    """Stateless Streamable HTTP MCP app (served at path ``/`` under ``/mcp``)."""
    global _mcp_http_ready
    ensure_tools_registered()
    inner = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )
    # Avoid child Router 307 / → // style redirects under the mount.
    router = getattr(inner, "router", None)
    if router is not None and hasattr(router, "redirect_slashes"):
        router.redirect_slashes = False
    _mcp_http_ready = True
    return McpAuthASGIMiddleware(inner)


class _McpPrefixDispatch:
    """Serve MCP at ``/mcp`` and ``/mcp/…`` without Starlette Mount's ``/mcp``→``/mcp/`` 307.

    Many MCP clients (Cursor etc.) do not re-send ``Authorization`` after a redirect.
    """

    def __init__(self, mcp_app: ASGIApp, prefix: str = "/mcp"):
        self.mcp_app = mcp_app
        self.prefix = prefix.rstrip("/") or "/mcp"

    def matches(self, path: str) -> bool:
        p = self.prefix
        if path == p:
            return True
        if path.startswith(p + "/"):
            # Let OAuth discovery under /mcp/.well-known fall through to FastAPI.
            rest = path[len(p) :]
            if rest.startswith("/.well-known"):
                return False
            return True
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.mcp_app(scope, receive, send)
            return
        path = scope.get("path") or ""
        p = self.prefix
        rest = path[len(p) :] or "/"
        if not rest.startswith("/"):
            rest = "/" + rest
        child: Scope = dict(scope)
        child["path"] = rest
        child["root_path"] = (scope.get("root_path") or "") + p
        if "raw_path" in child:
            child["raw_path"] = rest.encode("utf-8")
        await self.mcp_app(child, receive, send)


class _McpPrefixMiddleware:
    """Intercept ``/mcp`` before FastAPI routing so Mount never 307-redirects."""

    def __init__(self, app: ASGIApp, dispatch: _McpPrefixDispatch):
        self.app = app
        self.dispatch = dispatch

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path") or ""
            if self.dispatch.matches(path):
                await self.dispatch(scope, receive, send)
                return
        await self.app(scope, receive, send)


@asynccontextmanager
async def mcp_http_lifespan() -> AsyncIterator[None]:
    """Enter StreamableHTTP session_manager.run() (mounted apps skip Starlette lifespan)."""
    if not _mcp_http_ready:
        yield
        return
    async with mcp.session_manager.run():
        yield


def mount_http_mcp(app: Any) -> None:
    """Mount OAuth AS at ``/auth`` and HTTP MCP at ``/mcp`` (no trailing-slash redirect)."""
    try:
        mount_mcp_oauth(app)
    except Exception:  # noqa: BLE001
        logger.exception("failed to mount MCP OAuth (/auth); continuing without OAuth")

    try:
        mcp_app = build_http_mcp_app()
    except Exception:  # noqa: BLE001
        logger.exception("failed to build HTTP MCP app; /mcp not mounted")
        return

    dispatch = _McpPrefixDispatch(mcp_app, prefix="/mcp")
    # Outermost relative to later user traffic: add_middleware wraps existing stack.
    app.add_middleware(_McpPrefixMiddleware, dispatch=dispatch)
    logger.info("HTTP MCP at /mcp (no slash redirect; auth: agent_key or OAuth /auth)")
