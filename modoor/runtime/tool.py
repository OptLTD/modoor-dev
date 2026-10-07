"""Shared helpers for Module MCP tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from modoor.runtime.audit import write_audit
from modoor.runtime.auth import resolve_ctx
from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import get_settings


def ok(data: dict[str, Any]) -> str:
    return json.dumps({"status": "ok", "result": data}, ensure_ascii=False, default=str)


def err(exc: AppError) -> str:
    return json.dumps(exc.to_dict(), ensure_ascii=False)


def assert_agent_may_write(ctx: Ctx | None = None) -> None:
    """Raise if this Ctx is agent read-only (HTTP MCP default)."""
    c = ctx
    if c is None:
        c = resolve_ctx(get_settings())
    if getattr(c, "agent_readonly", False):
        raise AppError(
            "permission_denied",
            "Agent is read-only; mutating tools are disabled. "
            "Uncheck「Agent 只读」in Connect to Agent to allow writes.",
        )


def run_tool(
    tool: str,
    args: dict[str, Any],
    fn: Callable,
    *,
    readonly: bool = False,
) -> str:
    """Inject ctx, open DB session, audit, and normalize tool responses.

    Pass ``readonly=True`` for query tools so they remain available when the
    caller’s agent_key is in read-only mode (default for HTTP MCP).
    """
    settings = get_settings()
    try:
        ctx = resolve_ctx(settings)
        if getattr(ctx, "agent_readonly", False) and not readonly:
            raise AppError(
                "permission_denied",
                "Agent is read-only; mutating tools are disabled. "
                "Uncheck「Agent 只读」in Connect to Agent to allow writes.",
            )
        with session_scope() as session:
            result = fn(session, ctx, settings)
            status = (
                result.get("status")
                if isinstance(result, dict) and "status" in result
                else "ok"
            )
            write_audit(
                session,
                ctx=ctx,
                tool=tool,
                args=args,
                result_status=str(status),
            )
            if isinstance(result, dict) and result.get("status") == "needs_confirmation":
                return json.dumps(result, ensure_ascii=False, default=str)
            if isinstance(result, dict) and "status" in result:
                return json.dumps(result, ensure_ascii=False, default=str)
            return ok(result)
    except AppError as exc:
        try:
            ctx = resolve_ctx(settings)
            with session_scope() as session:
                write_audit(
                    session,
                    ctx=ctx,
                    tool=tool,
                    args=args,
                    result_status=exc.code,
                )
        except Exception:  # noqa: BLE001
            pass
        return err(exc)
