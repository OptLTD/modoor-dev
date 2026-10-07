"""Sale module MCP tools."""

from __future__ import annotations

from typing import Any

from modoor.runtime.confirmation import (
    issue_confirmation_token,
    needs_confirmation_payload,
    verify_confirmation_token,
)
from modoor.runtime.tool import run_tool
from addon.sale import domain as sale_domain


def register_adapters() -> None:
    from addon.sale.adapters import ensure_sale_adapters

    ensure_sale_adapters()


def create_order(
    partner: str,
    lines: list[dict[str, Any]],
    note: str | None = None,
) -> str:
    """Create a draft sales order.

    Args:
        partner: Customer display name (Phase 0 string; no partner module yet).
        lines: Order lines, each with product_name, qty, unit_price.
        note: Optional remark.
    """
    args = {"partner": partner, "lines": lines, "note": note}

    def _inner(session, ctx, _settings):
        return sale_domain.create_order(
            session,
            ctx,
            partner=partner,
            lines=lines,
            note=note,
        )

    return run_tool("sale.create_order", args, _inner)


def get_order(order_id: str) -> str:
    """Fetch a sales order by id (tenant-scoped)."""
    args = {"order_id": order_id}

    def _inner(session, ctx, _settings):
        return sale_domain.get_order(session, ctx, order_id)

    return run_tool("sale.get_order", args, _inner, readonly=True)


def confirm_order(
    order_id: str,
    confirmation_token: str | None = None,
) -> str:
    """Confirm a draft sales order (high risk).

    First call without confirmation_token returns status=needs_confirmation.
    After human/host approval, call again with the same order_id and confirmation_token.
    """
    args = {"order_id": order_id, "confirmation_token": confirmation_token}

    def _inner(session, ctx, settings):
        order = sale_domain.get_order(session, ctx, order_id)
        if confirmation_token:
            verify_confirmation_token(
                secret=settings.modoor_confirm_secret,
                ctx=ctx,
                tool="sale.confirm_order",
                args={"order_id": order_id},
                token=confirmation_token,
            )
            return sale_domain.confirm_order(session, ctx, order_id)

        token, expires_at = issue_confirmation_token(
            secret=settings.modoor_confirm_secret,
            ctx=ctx,
            tool="sale.confirm_order",
            args={"order_id": order_id},
            ttl_seconds=settings.modoor_confirm_ttl_seconds,
        )
        return needs_confirmation_payload(
            token=token,
            expires_at=expires_at,
            tool="sale.confirm_order",
            summary={
                "order_id": order["id"],
                "partner": order["partner"],
                "amount_total": order["amount_total"],
                "state": order["state"],
            },
            args={"order_id": order_id},
        )

    return run_tool("sale.confirm_order", args, _inner)


def register(mcp) -> None:
    register_adapters()
    mcp.tool(name="sale.create_order")(create_order)
    mcp.tool(name="sale.get_order")(get_order)
    mcp.tool(name="sale.confirm_order")(confirm_order)
