"""Resolve request Ctx: HTTP agent token (base_token) or legacy env API key."""

from __future__ import annotations

from contextvars import ContextVar

from sqlalchemy import select

from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import Settings
from builtin.base.domain import SystemUser, ensure_tenant, resolve_agent_auth, root_team_id

_request_ctx: ContextVar[Ctx | None] = ContextVar("modoor_request_ctx", default=None)


def bind_request_ctx(ctx: Ctx | None):
    """Bind Ctx for the current async/task context (HTTP MCP middleware)."""
    return _request_ctx.set(ctx)


def reset_request_ctx(token) -> None:
    _request_ctx.reset(token)


def current_request_ctx() -> Ctx | None:
    return _request_ctx.get()


def resolve_ctx(settings: Settings, provided_api_key: str | None = None) -> Ctx:
    """Resolve caller context.

    Order:
    1. Request-bound Ctx (HTTP MCP after agent token auth)
    2. Explicit key → match ``base_token`` (kind=agent)
    3. Explicit/env key → legacy ``MODOOR_API_KEY`` + env tenant/user
    """
    bound = _request_ctx.get()
    if bound is not None:
        return bound

    expected = settings.modoor_api_key
    key = provided_api_key if provided_api_key is not None else expected
    if not key:
        raise AppError(
            code="permission_denied",
            message="Invalid or missing API key",
        )

    with session_scope() as session:
        hit = resolve_agent_auth(session, key)
        if hit is not None:
            user, readonly = hit
            return Ctx(
                tenant=user.tenant,
                user_id=user.id,
                team_id=user.team_id,
                agent_readonly=readonly,
            )

        if key != expected:
            raise AppError(
                code="permission_denied",
                message="Invalid or missing API key",
            )

        ensured = ensure_tenant(
            session, settings.modoor_tenant, tenant_id=settings.modoor_tenant_id
        )
        tenant_id = int(ensured["tenant"]["id"])
        team_id = settings.modoor_team_id
        if team_id is None:
            team_id = root_team_id(session, tenant_id)
        user_id = settings.modoor_user_id
        if user_id is None:
            row = session.scalar(
                select(SystemUser)
                .where(SystemUser.tenant == tenant_id)
                .order_by(SystemUser.id)
            )
            user_id = int(row.id) if row else 0
        return Ctx(tenant=tenant_id, user_id=user_id, team_id=team_id)


def resolve_ctx_from_agent_key(key: str) -> Ctx:
    """Resolve Ctx strictly from ``base_token`` agent kind (HTTP MCP)."""
    raw = (key or "").strip()
    if not raw:
        raise AppError(code="permission_denied", message="Missing agent key")
    with session_scope() as session:
        hit = resolve_agent_auth(session, raw)
        if hit is None:
            raise AppError(code="permission_denied", message="Invalid agent key")
        user, readonly = hit
        return Ctx(
            tenant=user.tenant,
            user_id=user.id,
            team_id=user.team_id,
            agent_readonly=readonly,
        )
