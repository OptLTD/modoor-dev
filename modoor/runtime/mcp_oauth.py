"""MCP OAuth Authorization Server under ``/auth`` (browser login + consent).

Discovery for Cursor / MCP clients:
  401 on ``/mcp`` → ``/.well-known/oauth-protected-resource/mcp``
    → authorization_servers: ``{base}/auth``
    → ``/.well-known/oauth-authorization-server/auth``
  then ``/auth/authorize`` → login/consent → code → ``/auth/token``.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.metadata import MetadataHandler, ProtectedResourceMetadataHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.routes import (
    AUTHORIZATION_PATH,
    REGISTRATION_PATH,
    TOKEN_PATH,
    build_metadata,
    cors_middleware,
    create_auth_routes,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken, ProtectedResourceMetadata

from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from builtin.base import domain as base_domain

logger = logging.getLogger(__name__)

MCP_SCOPE = "mcp"
AUTH_MOUNT = "/auth"
CONSENT_PATH = "/consent"
TOKEN_TTL_SECONDS = 3600 * 8
CODE_TTL_SECONDS = 300
REFRESH_TTL_SECONDS = TOKEN_TTL_SECONDS * 7


def public_base_url() -> str:
    return str(get_settings().modoor_webui_url or "").rstrip("/")


def mcp_resource_url() -> str:
    return f"{public_base_url()}/mcp"


def mcp_issuer_url() -> str:
    """OAuth issuer = site origin (Cursor discovers ``/.well-known/oauth-authorization-server``)."""
    return public_base_url()


def auth_endpoint_base() -> str:
    """Physical OAuth endpoints live under ``/auth``."""
    return f"{public_base_url()}{AUTH_MOUNT}"


def resource_metadata_url() -> str:
    return f"{public_base_url()}/.well-known/oauth-protected-resource/mcp"


def as_metadata_url() -> str:
    return f"{public_base_url()}/.well-known/oauth-authorization-server"


class ModoorOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """In-process OAuth AS: DCR + PKCE + consent via Modoor session login."""

    def __init__(self) -> None:
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.state_mapping: dict[str, dict[str, Any]] = {}
        # code / refresh → {"readonly": bool}
        self._flags: dict[str, dict[str, Any]] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("No client_id provided")
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        state = params.state or secrets.token_hex(16)
        self.state_mapping[state] = {
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "client_id": client.client_id,
            "resource": params.resource,
            "scopes": list(params.scopes or [MCP_SCOPE]),
            "client_state": params.state,
            "client_name": getattr(client, "client_name", None) or client.client_id,
        }
        return f"{auth_endpoint_base()}{CONSENT_PATH}?state={quote(state, safe='')}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self.auth_codes.get(authorization_code)
        if code is None:
            return None
        if code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            self.auth_codes.pop(authorization_code, None)
            self._flags.pop(f"code:{authorization_code}", None)
            return None
        return code

    def _readonly_for_code(self, code: str) -> bool:
        return bool((self._flags.get(f"code:{code}") or {}).get("readonly", True))

    def _readonly_for_refresh(self, token: str) -> bool:
        return bool((self._flags.get(f"rt:{token}") or {}).get("readonly", True))

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")
        if not client.client_id:
            raise ValueError("No client_id provided")

        readonly = self._readonly_for_code(authorization_code.code)
        access = f"mcp_at_{secrets.token_hex(32)}"
        refresh = f"mcp_rt_{secrets.token_hex(32)}"
        expires_at = int(time.time()) + TOKEN_TTL_SECONDS

        self.tokens[access] = AccessToken(
            token=access,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=expires_at,
            resource=authorization_code.resource or mcp_resource_url(),
            subject=authorization_code.subject,
            claims={"readonly": readonly, "iss": mcp_issuer_url()},
        )
        self.refresh_tokens[refresh] = RefreshToken(
            token=refresh,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + REFRESH_TTL_SECONDS,
            subject=authorization_code.subject,
        )
        self._flags[f"rt:{refresh}"] = {"readonly": readonly}

        del self.auth_codes[authorization_code.code]
        self._flags.pop(f"code:{authorization_code.code}", None)

        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=TOKEN_TTL_SECONDS,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = self.tokens.get(token)
        if access is None:
            return None
        if access.expires_at and access.expires_at < int(time.time()):
            self.tokens.pop(token, None)
            return None
        return access

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = self.refresh_tokens.get(refresh_token)
        if row is None or row.client_id != client.client_id:
            return None
        if row.expires_at and row.expires_at < int(time.time()):
            self.refresh_tokens.pop(refresh_token, None)
            self._flags.pop(f"rt:{refresh_token}", None)
            return None
        return row

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if refresh_token.token not in self.refresh_tokens:
            raise ValueError("Invalid refresh token")
        if not client.client_id:
            raise ValueError("No client_id provided")

        use_scopes = scopes or refresh_token.scopes
        readonly = self._readonly_for_refresh(refresh_token.token)
        access = f"mcp_at_{secrets.token_hex(32)}"
        new_refresh = f"mcp_rt_{secrets.token_hex(32)}"
        expires_at = int(time.time()) + TOKEN_TTL_SECONDS

        self.tokens[access] = AccessToken(
            token=access,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=expires_at,
            resource=mcp_resource_url(),
            subject=refresh_token.subject,
            claims={"readonly": readonly, "iss": mcp_issuer_url()},
        )
        self.refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=int(time.time()) + REFRESH_TTL_SECONDS,
            subject=refresh_token.subject,
        )
        self._flags[f"rt:{new_refresh}"] = {"readonly": readonly}
        self.refresh_tokens.pop(refresh_token.token, None)
        self._flags.pop(f"rt:{refresh_token.token}", None)

        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=TOKEN_TTL_SECONDS,
            scope=" ".join(use_scopes),
            refresh_token=new_refresh,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        raw = token.token
        self.tokens.pop(raw, None)
        self.refresh_tokens.pop(raw, None)
        self._flags.pop(f"rt:{raw}", None)

    def issue_code_for_state(
        self,
        *,
        state: str,
        user_id: int,
        readonly: bool,
    ) -> str:
        pending = self.state_mapping.get(state)
        if not pending:
            raise ValueError("invalid_state")
        redirect_uri = str(pending["redirect_uri"])
        code = f"mcp_ac_{secrets.token_hex(24)}"
        self.auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=str(pending["client_id"]),
            redirect_uri=AnyHttpUrl(redirect_uri),
            redirect_uri_provided_explicitly=bool(
                pending.get("redirect_uri_provided_explicitly")
            ),
            expires_at=time.time() + CODE_TTL_SECONDS,
            scopes=list(pending.get("scopes") or [MCP_SCOPE]),
            code_challenge=str(pending["code_challenge"]),
            resource=pending.get("resource") or mcp_resource_url(),
            subject=str(user_id),
        )
        self._flags[f"code:{code}"] = {"readonly": readonly}

        client_state = pending.get("client_state")
        del self.state_mapping[state]
        kwargs: dict[str, str] = {"code": code}
        if client_state:
            kwargs["state"] = str(client_state)
        return construct_redirect_uri(redirect_uri, **kwargs)


_provider: ModoorOAuthProvider | None = None


def get_oauth_provider() -> ModoorOAuthProvider:
    global _provider
    if _provider is None:
        _provider = ModoorOAuthProvider()
    return _provider


def _client_registration_options() -> ClientRegistrationOptions:
    return ClientRegistrationOptions(
        enabled=True,
        valid_scopes=[MCP_SCOPE],
        default_scopes=[MCP_SCOPE],
    )


def _oauth_metadata(issuer: AnyHttpUrl):
    """AS metadata: issuer is site origin; endpoints under ``/auth``."""
    base = str(issuer).rstrip("/")
    auth = f"{base}{AUTH_MOUNT}"
    opts = _client_registration_options()
    meta = build_metadata(
        AnyHttpUrl(auth),  # build paths relative to /auth mount
        None,
        opts,
        RevocationOptions(enabled=False),
        supports_identity_assertion=False,
    )
    # Re-stamp issuer as site origin (common MCP client expectation).
    meta.issuer = issuer
    meta.authorization_endpoint = AnyHttpUrl(f"{auth}{AUTHORIZATION_PATH}")
    meta.token_endpoint = AnyHttpUrl(f"{auth}{TOKEN_PATH}")
    if opts.enabled:
        meta.registration_endpoint = AnyHttpUrl(f"{auth}{REGISTRATION_PATH}")
    methods = list(meta.token_endpoint_auth_methods_supported or [])
    if "none" not in methods:
        methods.append("none")
    meta.token_endpoint_auth_methods_supported = methods
    return meta


def _consent_html(
    *,
    state: str,
    client_name: str,
    username: str,
    error: str | None = None,
) -> str:
    err = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>授权 MCP · Modoor</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 420px; margin: 48px auto; padding: 0 16px; color: #1a1a1a; }}
    h1 {{ font-size: 1.35rem; margin-bottom: 0.35rem; }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1.25rem; margin-top: 1.25rem; }}
    label.row {{ display: flex; gap: 0.5rem; align-items: flex-start; margin: 1rem 0; font-size: 0.9rem; }}
    .actions {{ display: flex; gap: 0.75rem; margin-top: 1.25rem; }}
    button {{ flex: 1; padding: 0.65rem 1rem; border-radius: 6px; border: 1px solid #ccc; cursor: pointer; font-size: 0.95rem; }}
    button.primary {{ background: #1a1a1a; color: #fff; border-color: #1a1a1a; }}
    .error {{ color: #b00020; }}
    code {{ font-size: 0.85rem; word-break: break-all; }}
  </style>
</head>
<body>
  <h1>授权 MCP 访问</h1>
  <p class="muted">已登录为 <strong>{username}</strong></p>
  <div class="card">
    <p><strong>{client_name}</strong> 请求访问 Modoor MCP（工具 / 资源）。</p>
    <p class="muted">资源：<code>{mcp_resource_url()}</code></p>
    {err}
    <form method="post" action="{AUTH_MOUNT}{CONSENT_PATH}">
      <input type="hidden" name="state" value="{state}" />
      <label class="row">
        <input type="checkbox" name="allow_write" value="1" />
        <span>允许写入（关闭只读；默认只读查询）</span>
      </label>
      <div class="actions">
        <button type="submit" name="decision" value="deny">拒绝</button>
        <button type="submit" name="decision" value="allow" class="primary">授权</button>
      </div>
    </form>
  </div>
</body>
</html>"""


def _current_user_id(request: Request) -> int | None:
    uid = request.session.get("user_id") if hasattr(request, "session") else None
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def _core_auth_routes(provider: ModoorOAuthProvider) -> list[Route]:
    authenticator = ClientAuthenticator(provider)
    opts = _client_registration_options()
    return [
        Route(
            AUTHORIZATION_PATH,
            endpoint=AuthorizationHandler(provider).handle,
            methods=["GET", "POST"],
        ),
        Route(
            TOKEN_PATH,
            endpoint=cors_middleware(TokenHandler(provider, authenticator).handle, ["POST", "OPTIONS"]),
            methods=["POST", "OPTIONS"],
        ),
        Route(
            REGISTRATION_PATH,
            endpoint=cors_middleware(
                RegistrationHandler(provider, options=opts).handle, ["POST", "OPTIONS"]
            ),
            methods=["POST", "OPTIONS"],
        ),
    ]


def build_oauth_as_app() -> Starlette:
    """Starlette app mounted at ``/auth``."""
    provider = get_oauth_provider()
    # Route builder validates issuer; use /auth URL (loopback HTTP allowed).
    route_issuer = AnyHttpUrl(auth_endpoint_base())

    try:
        routes = create_auth_routes(
            provider=provider,
            issuer_url=route_issuer,
            client_registration_options=_client_registration_options(),
            revocation_options=RevocationOptions(enabled=False),
        )
    except ValueError as exc:
        # Non-loopback HTTP (LAN IP): SDK rejects issuer; mount endpoints anyway.
        logger.warning("OAuth issuer URL check failed (%s); mounting without HTTPS guard", exc)
        routes = _core_auth_routes(provider)

    # Parent app serves discovery; drop nested well-known from the mount.
    routes = [
        r
        for r in routes
        if getattr(r, "path", "") != "/.well-known/oauth-authorization-server"
    ]

    async def consent_get(request: Request) -> Response:
        state = (request.query_params.get("state") or "").strip()
        if not state or state not in provider.state_mapping:
            return HTMLResponse("<p>无效或过期的授权请求</p>", status_code=400)
        user_id = _current_user_id(request)
        if user_id is None:
            next_url = f"{AUTH_MOUNT}{CONSENT_PATH}?{urlencode({'state': state})}"
            return RedirectResponse(f"/login?next={quote(next_url, safe='')}", status_code=302)
        with session_scope() as session:
            user = base_domain.load_user(session, user_id)
            if user is None or not user.active:
                next_url = f"{AUTH_MOUNT}{CONSENT_PATH}?{urlencode({'state': state})}"
                return RedirectResponse(f"/login?next={quote(next_url, safe='')}", status_code=302)
            username = user.username
        pending = provider.state_mapping[state]
        return HTMLResponse(
            _consent_html(
                state=state,
                client_name=str(pending.get("client_name") or "MCP Client"),
                username=username,
            )
        )

    async def consent_post(request: Request) -> Response:
        form = await request.form()
        state = str(form.get("state") or "").strip()
        decision = str(form.get("decision") or "").strip()
        allow_write = str(form.get("allow_write") or "") == "1"
        pending = provider.state_mapping.get(state)
        if not pending:
            return HTMLResponse("<p>无效或过期的授权请求</p>", status_code=400)
        user_id = _current_user_id(request)
        if user_id is None:
            next_url = f"{AUTH_MOUNT}{CONSENT_PATH}?{urlencode({'state': state})}"
            return RedirectResponse(f"/login?next={quote(next_url, safe='')}", status_code=302)

        redirect_uri = str(pending["redirect_uri"])
        client_state = pending.get("client_state")
        if decision != "allow":
            provider.state_mapping.pop(state, None)
            kwargs: dict[str, str] = {
                "error": "access_denied",
                "error_description": "user denied",
            }
            if client_state:
                kwargs["state"] = str(client_state)
            return RedirectResponse(construct_redirect_uri(redirect_uri, **kwargs), status_code=302)

        try:
            url = provider.issue_code_for_state(
                state=state, user_id=user_id, readonly=not allow_write
            )
        except ValueError:
            return HTMLResponse("<p>授权失败：状态无效</p>", status_code=400)
        return RedirectResponse(url, status_code=302)

    routes.extend(
        [
            Route(CONSENT_PATH, endpoint=consent_get, methods=["GET"]),
            Route(CONSENT_PATH, endpoint=consent_post, methods=["POST"]),
        ]
    )
    return Starlette(routes=routes)


def mount_mcp_oauth(app: Any) -> None:
    """Mount AS endpoints at ``/auth`` + well-known discovery on the parent app."""
    issuer = AnyHttpUrl(mcp_issuer_url())
    resource = AnyHttpUrl(mcp_resource_url())
    as_meta = _oauth_metadata(issuer)
    pr_meta = ProtectedResourceMetadata(
        resource=resource,
        authorization_servers=[issuer],
        scopes_supported=[MCP_SCOPE],
        resource_name="Modoor MCP",
        bearer_methods_supported=["header"],
    )

    app.mount(AUTH_MOUNT, build_oauth_as_app())

    as_handler = cors_middleware(MetadataHandler(as_meta).handle, ["GET", "OPTIONS"])
    pr_handler = cors_middleware(ProtectedResourceMetadataHandler(pr_meta).handle, ["GET", "OPTIONS"])

    # Primary discovery (issuer = origin)
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        # Path-aware / legacy probes some clients still hit
        f"/.well-known/oauth-authorization-server{AUTH_MOUNT}",
        f"/.well-known/openid-configuration{AUTH_MOUNT}",
        f"{AUTH_MOUNT}/.well-known/oauth-authorization-server",
        f"{AUTH_MOUNT}/.well-known/openid-configuration",
    ):
        app.add_route(path, as_handler, methods=["GET", "OPTIONS"])

    for path in (
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-protected-resource",
    ):
        app.add_route(path, pr_handler, methods=["GET", "OPTIONS"])

    logger.info(
        "MCP OAuth issuer=%s endpoints=%s/* resource=%s",
        mcp_issuer_url(),
        auth_endpoint_base(),
        mcp_resource_url(),
    )
