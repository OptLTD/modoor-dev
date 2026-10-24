from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Integer, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError
from modoor.core.state import SALE_CONFIRMED, SALE_DRAFT, sale_label


class SaleOrder(Base):
    __tablename__ = "sale_order"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    created_by: Mapped[int] = mapped_column(Integer)
    partner: Mapped[str] = mapped_column(String(256))
    state: Mapped[int] = mapped_column(SmallInteger, default=SALE_DRAFT)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list[SaleOrderLine]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class SaleOrderLine(Base):
    __tablename__ = "sale_order_line"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("sale_order.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(256))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    order: Mapped[SaleOrder] = relationship(back_populates="lines")


def _order_to_dict(order: SaleOrder) -> dict[str, Any]:
    lines = [
        {
            "id": line.id,
            "product_name": line.product_name,
            "qty": float(line.qty),
            "unit_price": float(line.unit_price),
            "amount": float(line.qty * line.unit_price),
        }
        for line in order.lines
    ]
    total = sum(item["amount"] for item in lines)
    return {
        "id": order.id,
        "tenant": order.tenant,
        "team_id": order.team_id,
        "created_by": order.created_by,
        "partner": order.partner,
        "state": sale_label(order.state),
        "note": order.note,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "lines": lines,
        "amount_total": total,
    }


def _get_order(session: Session, ctx: Ctx, order_id: str) -> SaleOrder:
    order = session.get(SaleOrder, order_id)
    if order is None or order.tenant != ctx.tenant:
        raise AppError("not_found", f"Order not found: {order_id}")
    return order


def create_order(
    session: Session,
    ctx: Ctx,
    *,
    partner: str,
    lines: list[dict[str, Any]],
    note: str | None = None,
) -> dict[str, Any]:
    if not partner.strip():
        raise AppError("validation_error", "partner is required")
    if not lines:
        raise AppError("validation_error", "at least one line is required")

    order = SaleOrder(
        id=str(uuid.uuid4()),
        tenant=ctx.tenant,
        team_id=ctx.team_id,
        created_by=ctx.user_id,
        partner=partner.strip(),
        state=SALE_DRAFT,
        note=note,
    )
    for raw in lines:
        product_name = str(raw.get("product_name") or "").strip()
        if not product_name:
            raise AppError("validation_error", "line.product_name is required")
        try:
            qty = Decimal(str(raw["qty"]))
            unit_price = Decimal(str(raw["unit_price"]))
        except Exception as exc:  # noqa: BLE001
            raise AppError("validation_error", "invalid qty or unit_price") from exc
        if qty <= 0:
            raise AppError("validation_error", "qty must be > 0")
        order.lines.append(
            SaleOrderLine(
                id=str(uuid.uuid4()),
                product_name=product_name,
                qty=qty,
                unit_price=unit_price,
            )
        )
    session.add(order)
    session.flush()
    return _order_to_dict(order)


def get_order(session: Session, ctx: Ctx, order_id: str) -> dict[str, Any]:
    return _order_to_dict(_get_order(session, ctx, order_id))


def confirm_order(session: Session, ctx: Ctx, order_id: str) -> dict[str, Any]:
    order = _get_order(session, ctx, order_id)
    if int(order.state or 0) == SALE_CONFIRMED:
        raise AppError("conflict", "Order already confirmed", details={"order_id": order_id})
    if int(order.state or 0) != SALE_DRAFT:
        raise AppError("conflict", f"Cannot confirm order in state={sale_label(order.state)}")
    order.state = SALE_CONFIRMED
    order.confirmed_at = datetime.now(timezone.utc)
    session.flush()
    return _order_to_dict(order)


# Demo partners / products for local bootstrap (idempotent).
_DEMO_ORDERS: list[dict[str, Any]] = [
    {
        "partner": "星海科技",
        "note": "首单试用",
        "confirm": False,
        "lines": [
            {"product_name": "标准订阅 · 月", "qty": 3, "unit_price": 299},
            {"product_name": "实施服务", "qty": 1, "unit_price": 4800},
        ],
    },
    {
        "partner": "青禾商贸",
        "note": "老客户续约",
        "confirm": True,
        "lines": [
            {"product_name": "专业订阅 · 年", "qty": 1, "unit_price": 12800},
            {"product_name": "额外席位", "qty": 5, "unit_price": 180},
        ],
    },
    {
        "partner": "云启物流",
        "note": None,
        "confirm": True,
        "lines": [
            {"product_name": "车队看板模块", "qty": 2, "unit_price": 3600},
            {"product_name": "数据迁移", "qty": 1, "unit_price": 2200},
        ],
    },
    {
        "partner": "北岸设计",
        "note": "待确认报价",
        "confirm": False,
        "lines": [
            {"product_name": "设计协作席位", "qty": 8, "unit_price": 99},
        ],
    },
    {
        "partner": "禾田食品",
        "note": "季度框架",
        "confirm": True,
        "lines": [
            {"product_name": "门店收银插件", "qty": 12, "unit_price": 450},
            {"product_name": "培训（天）", "qty": 2, "unit_price": 1500},
        ],
    },
]


def seed_demo_orders(session: Session, ctx: Ctx, *, force: bool = False) -> int:
    """Insert demo sale orders. Skips when tenant already has rows unless force=True."""
    if not force:
        existing = session.scalar(
            select(func.count()).select_from(SaleOrder).where(SaleOrder.tenant == ctx.tenant)
        )
        if existing:
            return 0
    created = 0
    for spec in _DEMO_ORDERS:
        order = create_order(
            session,
            ctx,
            partner=str(spec["partner"]),
            lines=list(spec["lines"]),
            note=spec.get("note"),
        )
        if spec.get("confirm"):
            confirm_order(session, ctx, order["id"])
        created += 1
    return created
