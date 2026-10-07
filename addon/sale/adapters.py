"""Sale model adapters: schema index ↔ domain ORM."""

from __future__ import annotations

from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.core.state import sale_code, sale_label
from modoor.engine.adapters import (
    ModelAdapter,
    flatten_pick,
    normalize_batch_row,
    register_adapter,
)
from modoor.engine.oplog import diff_row_values, record_oplog
from modoor.engine.query import QueryTerm, parse_query


def _as_sale_state(val: Any) -> int | list[int]:
    if isinstance(val, list):
        return [sale_code(v) for v in val]
    return sale_code(val)


class SaleOrderAdapter(ModelAdapter):
    model = "sale.order"

    # schema index → ORM attribute
    COLS: dict[str, str] = {
        "basic.uukey": "id",
        "basic.utime": "created_at",
        "basic.status": "state",
        "basic.partner": "partner",
        "basic.note": "note",
    }

    def _to_values(self, order: Any, field_keys: list[str] | None = None) -> dict[str, Any]:
        total = sum((line.qty * line.unit_price) for line in (order.lines or []))
        raw = {
            "basic.uukey": order.id,
            "basic.utime": order.created_at.isoformat() if order.created_at else None,
            "basic.status": sale_label(order.state),
            "basic.partner": order.partner,
            "basic.note": order.note,
            "amount.total": float(total),
        }
        if field_keys is None:
            return raw
        return {k: raw.get(k) for k in field_keys if k in raw}

    def _apply_terms(self, stmt: Any, terms: list[QueryTerm]) -> Any:
        from addon.sale.domain import SaleOrder

        for term in terms:
            col_name = self.COLS.get(term.field)
            if not col_name:
                continue
            col = getattr(SaleOrder, col_name)
            op = term.op
            val = term.value
            if term.field == "basic.status":
                val = _as_sale_state(val)
            if op == "EQ":
                stmt = stmt.where(col == val)
            elif op == "NE":
                stmt = stmt.where(col != val)
            elif op == "IN":
                vals = val if isinstance(val, list) else [val]
                stmt = stmt.where(col.in_(vals))
            elif op == "LIKE":
                stmt = stmt.where(col.ilike(f"%{val}%") if hasattr(col, "ilike") else col.like(f"%{val}%"))
            elif op == "NIL":
                if val in (True, "true", 1, "1"):
                    stmt = stmt.where(col.is_(None))
                else:
                    stmt = stmt.where(col.is_not(None))
            elif op == "BTW" and isinstance(val, (list, tuple)) and len(val) >= 2:
                stmt = stmt.where(col >= val[0], col <= val[1])
            elif op == "GT":
                stmt = stmt.where(col > val)
            elif op == "GTE":
                stmt = stmt.where(col >= val)
            elif op == "LT":
                stmt = stmt.where(col < val)
            elif op == "LTE":
                stmt = stmt.where(col <= val)
        return stmt

    def search(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        order: dict[str, Any] | None,
        page: int,
        size: int,
        field_keys: list[str],
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
        from addon.sale.domain import SaleOrder

        page = max(int(page or 1), 1)
        size = min(max(int(size or 50), 1), 500)
        terms = parse_query(query)
        base = select(SaleOrder).where(SaleOrder.tenant == ctx.tenant)
        base = self._apply_terms(base, terms)

        count = session.scalar(select(func.count()).select_from(base.subquery())) or 0

        order_field = (order or {}).get("field") or "basic.uukey"
        order_dir = str((order or {}).get("order") or "desc").lower()
        col_name = self.COLS.get(str(order_field), "id")
        col = getattr(SaleOrder, col_name, SaleOrder.id)
        ordered = base.order_by(desc(col) if order_dir == "desc" else asc(col))
        rows = session.scalars(
            ordered.options(selectinload(SaleOrder.lines)).offset((page - 1) * size).limit(size)
        ).all()
        values = [self._to_values(r, field_keys) for r in rows]

        totals: dict[str, Any] | None = None
        if "amount.total" in field_keys and values:
            totals = {
                "basic.uukey": len(values),
                "amount.total": round(sum(float(v.get("amount.total") or 0) for v in values), 2),
            }
        return values, int(count), totals

    def get_values(self, session: Session, ctx: Ctx, uukey: str) -> dict[str, Any] | None:
        from addon.sale.domain import SaleOrder

        order = session.get(SaleOrder, uukey)
        if order is None or order.tenant != ctx.tenant:
            return None
        return self._to_values(order)

    def upsert(
        self,
        session: Session,
        ctx: Ctx,
        batch: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from addon.sale import domain as sale_domain
        from addon.sale.domain import SaleOrder

        records: list[dict[str, Any]] = []
        for raw in batch:
            row = normalize_batch_row(raw)
            uukey = str(row.get("basic.uukey") or row.get("uukey") or "").strip()
            partner = str(flatten_pick(row, "basic.partner") or "").strip()
            status = flatten_pick(row, "basic.status")
            note = flatten_pick(row, "basic.note")

            existing = session.get(SaleOrder, uukey) if uukey else None
            if existing and existing.tenant == ctx.tenant:
                before = self._to_values(existing)
                if partner:
                    existing.partner = partner
                if status not in (None, ""):
                    existing.state = sale_code(status)
                if note is not None:
                    existing.note = str(note) if note != "" else None
                session.flush()
                current = self._to_values(existing)
                changes = diff_row_values(before, current)
                if changes:
                    record_oplog(
                        session,
                        ctx,
                        code=existing.id,
                        action="UPDATE",
                        model=self.model,
                        before=before,
                        after=current,
                        diff=changes,
                    )
                records.append(
                    {
                        "uukey": existing.id,
                        "model": self.model,
                        "opType": "UPDATE",
                        "exists": True,
                        "request": row,
                        "current": current,
                        "prepare": current,
                        "storage": {"basic": {
                            "uukey": existing.id,
                            "partner": existing.partner,
                            "status": sale_label(existing.state),
                            "note": existing.note,
                        }},
                        "changed": bool(changes),
                        "changes": changes,
                        "objects": None,
                    }
                )
                continue

            # create — require partner; add placeholder line if none
            if not partner:
                raise AppError("validation_error", "basic.partner is required")
            created = sale_domain.create_order(
                session,
                ctx,
                partner=partner,
                lines=[{"product_name": "-", "qty": 1, "unit_price": 0}],
                note=str(note) if note not in (None, "") else None,
            )
            # if client sent preferred id and create used uuid — keep uuid as truth
            entity = session.get(SaleOrder, created["id"])
            assert entity is not None
            if status not in (None, "") and sale_code(status) != sale_code("draft"):
                entity.state = sale_code(status)
                session.flush()
            current = self._to_values(entity)
            changes = diff_row_values(None, current)
            record_oplog(
                session,
                ctx,
                code=entity.id,
                action="INSERT",
                model=self.model,
                before=None,
                after=current,
                diff=changes,
            )
            records.append(
                {
                    "uukey": entity.id,
                    "model": self.model,
                    "opType": "INSERT",
                    "exists": False,
                    "request": row,
                    "current": current,
                    "prepare": current,
                    "storage": {"basic": {
                        "uukey": entity.id,
                        "partner": entity.partner,
                        "status": sale_label(entity.state),
                        "note": entity.note,
                    }},
                    "changed": True,
                    "changes": changes,
                    "objects": None,
                }
            )
        return records

    def delete_keys(self, session: Session, ctx: Ctx, keys: list[str]) -> None:
        from addon.sale.domain import SaleOrder

        for key in keys:
            order = session.get(SaleOrder, key)
            if order is None or order.tenant != ctx.tenant:
                continue
            before = self._to_values(order)
            code = order.id
            session.delete(order)
            record_oplog(
                session,
                ctx,
                code=code,
                action="DELETE",
                model=self.model,
                before=before,
                after=None,
            )
        session.flush()


def ensure_sale_adapters() -> None:
    from modoor.engine import adapters as eng

    if "sale.order" not in eng._ADAPTERS:
        register_adapter(SaleOrderAdapter())


ensure_sale_adapters()
