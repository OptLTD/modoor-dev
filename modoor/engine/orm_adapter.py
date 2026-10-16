"""COLS-driven ORM adapter — shared search / totals / facets for all modules.

Modules declare ``COLS`` / ``JSON_GROUPS`` / ``NUM_KEYS`` / ``DT_KEYS`` / ``LIST_KEYS`` and inherit
``ColsOrmAdapter``. Fleet-specific serial / uterm hooks override thin methods.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import Float, JSON, String, and_, asc, case, cast, desc, distinct, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.engine.adapters import ModelAdapter, flatten_pick, normalize_batch_row
from modoor.engine.query import QueryTerm, parse_query, resolve_list_order

FACET_TYPES = frozenset(
    {
        "RELATION",
        "OPTIONAL",
        "STRINGS",
        "SUBJECT",
        "KEYWORDS",
        "DATETIME",
    }
)

# 合计行用 distinct 的字段类型（分类文本 + 日期/月份）
UNIQUE_TOTAL_TYPES = frozenset(
    {
        "RELATION",
        "OPTIONAL",
        "STRINGS",
        "SUBJECT",
        "KEYWORDS",
        "DATETIME",
    }
)


def parse_dt(val: Any) -> datetime | None:
    if val in (None, ""):
        return None
    s = str(val).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # ONLYMONTH：YYYY-MM → 当月 1 日
    if len(s) == 7 and s[4] == "-" and s[:4].isdigit() and s[5:7].isdigit():
        s = f"{s}-01T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise AppError("validation_error", f"invalid datetime: {val}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_dt_bound(val: Any, *, end: bool = False) -> datetime | None:
    """Parse query bound; bare YYYY-MM-DD becomes start/end of that UTC day."""
    if val in (None, ""):
        return None
    s = str(val).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        dt = parse_dt(s)
        if dt is None:
            return None
        if end:
            return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return parse_dt(s)


def to_dec(val: Any) -> Decimal | None:
    if val in (None, ""):
        return None
    return Decimal(str(val))


def to_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def to_float(val: Decimal | float | int | None) -> float | None:
    if val is None:
        return None
    return float(val)


class ColsOrmAdapter(ModelAdapter):
    """Generic adapter: schema_key → ORM attr (+ optional JSON group coerce).

    GROUPED 字段：``JSON_GROUPS`` 列出组名，COLS 仍用 ``group.field`` → 组内 key；
    ORM 上对应同名 JSON 列。
    """

    model: str
    entity_cls: type
    COLS: dict[str, str]
    DT_KEYS: set[str] = set()
    NUM_KEYS: set[str] = set()
    # JSON 数组列。筛选 IN/EQ 按「包含任一」，与内存里的多选字段一致。
    LIST_KEYS: set[str] = set()
    REQUIRED_ON_CREATE: list[str] = []
    JSON_GROUPS: set[str] = set()
    after_upsert: Callable[[Session, Ctx, Any, dict[str, Any], bool], None] | None = None
    # Write base.oplog on INSERT/UPDATE/DELETE (model field diff).
    AUDIT_OPLOG: bool = True

    def _serial_meta(self) -> tuple[str, int]:
        return ("X", 5)

    def _alloc_uukey(self, session: Session, ctx: Ctx) -> str:
        """Reserve next business serial. Subclasses should override."""
        prefix, width = self._serial_meta()
        raise AppError(
            "validation_error",
            f"{self.model}: alloc_uukey not implemented (prefix={prefix}, width={width})",
        )

    def _biz_code(self, row: Any) -> str:
        return str(getattr(row, "uukey", None) or getattr(row, "id", "") or "").strip()

    def _json_path(self, sk: str) -> tuple[str, str] | None:
        if "." not in sk:
            return None
        group, field = sk.split(".", 1)
        if group in self.JSON_GROUPS:
            return group, field
        return None

    def _json_element(self, col: Any, field: str) -> Any:
        return col.op("->")(literal(field))

    def _json_number(self, col: Any, field: str) -> Any:
        """数值键类型固定。用 jsonb 的 -> 转数字，不再先 ->> 成文本。"""
        element = self._json_element(col, field)
        return case((func.jsonb_typeof(element) == "number", cast(element, Float)))

    def _json_text_expr(self, group: str, field: str) -> Any:
        col = getattr(self.entity_cls, group)
        return col[field].as_string()

    def _json_num_expr(self, group: str, field: str) -> Any:
        return self._json_number(getattr(self.entity_cls, group), field)

    def _resolve(self, session: Session, ctx: Ctx, key: str) -> Any | None:
        cls = self.entity_cls
        k = str(key or "").strip()
        if not k:
            return None
        row = session.get(cls, k)
        if row is not None and row.tenant == ctx.tenant:
            return row
        if hasattr(cls, "uukey"):
            row = session.scalar(
                select(cls).where(cls.tenant == ctx.tenant, cls.uukey == k).limit(1)
            )
            if row is not None:
                return row
        return None

    def _resolve_fk_id(self, session: Session, ctx: Ctx, target_cls: type, key: str) -> str:
        k = str(key or "").strip()
        if not k:
            return k
        row = session.get(target_cls, k)
        if row is not None and getattr(row, "tenant", None) == ctx.tenant:
            return str(row.id)
        if hasattr(target_cls, "uukey"):
            row = session.scalar(
                select(target_cls)
                .where(target_cls.tenant == ctx.tenant, target_cls.uukey == k)
                .limit(1)
            )
            if row is not None:
                return str(row.id)
        return k

    def _normalize_fks(self, session: Session, ctx: Ctx, entity: Any) -> None:
        for attr, target in getattr(self, "FK_ATTRS", {}).items():
            raw = getattr(entity, attr, None)
            if raw in (None, ""):
                continue
            setattr(entity, attr, self._resolve_fk_id(session, ctx, target, str(raw)))

    def _read_col(self, row: Any, sk: str, attr: str) -> Any:
        path = self._json_path(sk)
        if path:
            group, field = path
            blob = getattr(row, group, None) or {}
            if not isinstance(blob, dict):
                return None
            return blob.get(field)
        return getattr(row, attr, None)

    def _to_values(self, row: Any, field_keys: list[str] | None = None) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        for sk, attr in self.COLS.items():
            val = self._read_col(row, sk, attr)
            if sk == "basic.uukey":
                raw[sk] = self._biz_code(row)
                continue
            if sk in self.DT_KEYS or isinstance(val, datetime):
                raw[sk] = to_iso(val) if isinstance(val, datetime) else val
            elif isinstance(val, Decimal):
                raw[sk] = to_float(val)
            else:
                raw[sk] = val
        if field_keys is None:
            return raw
        return {k: raw.get(k) for k in field_keys if k in raw}

    def _coerce_query_val(self, field: str, op: str, val: Any) -> Any:
        if op in ("NIL", "NNL", "LIKE"):
            return val
        if field not in self.DT_KEYS:
            if field in self.NUM_KEYS:
                if op == "IN":
                    return [to_dec(v) for v in (val if isinstance(val, list) else [val])]
                if op == "BTW" and isinstance(val, (list, tuple)) and len(val) >= 2:
                    return [to_dec(val[0]), to_dec(val[1])]
                return to_dec(val)
            return val
        as_json = bool(self._json_path(field))

        def _one(v: Any, *, end: bool = False) -> Any:
            d = parse_dt_bound(v, end=end)
            return to_iso(d) if as_json and isinstance(d, datetime) else d

        if op == "IN":
            return [_one(v) for v in (val if isinstance(val, list) else [val])]
        if op == "BTW" and isinstance(val, (list, tuple)) and len(val) >= 2:
            return [_one(val[0], end=False), _one(val[1], end=True)]
        if op in ("LT", "LTE"):
            return _one(val, end=True)
        return _one(val, end=False)

    def _term_clause(self, term: QueryTerm) -> Any | None:
        cls = self.entity_cls
        path = self._json_path(term.field)
        if path:
            group, field = path
            if not hasattr(cls, group):
                return None
            op = term.op
            val = self._coerce_query_val(term.field, op, term.value)
            text = self._json_text_expr(group, field)
            if op == "NIL" and term.field in self.NUM_KEYS:
                element = self._json_element(getattr(cls, group), field)
                missing = or_(element.is_(None), func.jsonb_typeof(element) != "number")
                return missing if val in (True, "true", 1, "1") else ~missing
            if op == "NIL":
                missing = or_(text.is_(None), text == "", text == "null")
                return missing if val in (True, "true", 1, "1") else ~missing
            if term.field in self.NUM_KEYS and op not in ("LIKE", "IN"):
                num = self._json_num_expr(group, field)
                if op == "EQ":
                    return num == val
                if op == "NE":
                    return num != val
                if op == "GT":
                    return num > val
                if op == "GTE":
                    return num >= val
                if op == "LT":
                    return num < val
                if op == "LTE":
                    return num <= val
                if op == "BTW" and isinstance(val, (list, tuple)) and len(val) >= 2:
                    return and_(num >= val[0], num <= val[1])
                return None
            if op == "EQ":
                return text == val
            if op == "NE":
                return text != val
            if op == "IN":
                vals = val if isinstance(val, list) else [val]
                return text.in_([str(v) for v in vals])
            if op == "LIKE":
                return text.like(f"%{val}%")
            if op == "BTW" and isinstance(val, (list, tuple)) and len(val) >= 2:
                day = func.left(text, 10)
                lo = str(val[0])[:10]
                hi = str(val[1])[:10]
                return and_(day >= lo, day <= hi)
            return None

        col_name = self.COLS.get(term.field)
        if not col_name or not hasattr(cls, col_name):
            return None
        col = getattr(cls, col_name)
        op = term.op
        val = self._coerce_query_val(term.field, op, term.value)
        if term.field in self.LIST_KEYS:
            return self._list_clause(col, op, val)
        if op == "EQ":
            return col == val
        if op == "NE":
            return col != val
        if op == "IN":
            vals = val if isinstance(val, list) else [val]
            return col.in_(vals)
        if op == "LIKE":
            return col.ilike(f"%{val}%") if hasattr(col, "ilike") else col.like(f"%{val}%")
        if op == "NIL":
            return col.is_(None) if val in (True, "true", 1, "1") else col.is_not(None)
        if op == "BTW" and isinstance(val, (list, tuple)) and len(val) >= 2:
            return and_(col >= val[0], col <= val[1])
        if op == "GT":
            return col > val
        if op == "GTE":
            return col >= val
        if op == "LT":
            return col < val
        if op == "LTE":
            return col <= val
        return None

    def _apply_terms(self, stmt: Any, terms: list[QueryTerm]) -> Any:
        ands: list[Any] = []
        or_groups: dict[str, list[Any]] = {}
        for term in terms:
            clause = self._term_clause(term)
            if clause is None:
                continue
            g = str(getattr(term, "group", "") or "")
            if g == "or" or g.startswith("or:"):
                or_groups.setdefault(g, []).append(clause)
            else:
                ands.append(clause)
        for c in ands:
            stmt = stmt.where(c)
        for clauses in or_groups.values():
            stmt = stmt.where(or_(*clauses))
        return stmt

    def _terms_clause(self, terms: list[QueryTerm]) -> Any | None:
        """把一组条件收成一个布尔表达式，供聚合 FILTER 使用。"""
        ands: list[Any] = []
        or_groups: dict[str, list[Any]] = {}
        for term in terms:
            clause = self._term_clause(term)
            if clause is None:
                continue
            group = str(getattr(term, "group", "") or "")
            if group == "or" or group.startswith("or:"):
                or_groups.setdefault(group, []).append(clause)
            else:
                ands.append(clause)
        parts = list(ands)
        for clauses in or_groups.values():
            parts.append(or_(*clauses) if len(clauses) > 1 else clauses[0])
        if not parts:
            return None
        return and_(*parts) if len(parts) > 1 else parts[0]

    def digest(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        group_by: list[dict[str, str]],
        count_fn: list[dict[str, str]],
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
        """GROUP BY + aggregate metrics; returns (rows, group_count, grand_totals)."""
        cls = self.entity_cls
        page = max(int(page or 1), 1)
        size = min(max(int(size or 50), 1), 500)
        terms = parse_query(query)

        g_exprs: list[Any] = []
        g_keys: list[str] = []
        for g in group_by:
            sk = str(g.get("index") or "").strip()
            if not sk:
                continue
            fmt = str(g.get("format") or "").lower()
            expr = self._value_expr(
                sk,
                as_date=(fmt == "date"),
                as_month=(fmt == "month"),
            )
            if expr is None:
                continue
            g_exprs.append(expr.label(f"g_{len(g_keys)}"))
            g_keys.append(sk)

        if not g_keys or not count_fn:
            return [], 0, None

        a_exprs: list[Any] = []
        a_keys: list[str] = []
        for c in count_fn:
            sk = str(c.get("index") or "").strip()
            fn = str(c.get("func") or "SUM").upper()
            if not sk:
                continue
            base = self._value_expr(sk)
            if fn == "CNT":
                expr = func.count() if base is None else func.count(base)
            elif fn == "UNQ":
                if base is None:
                    continue
                expr = func.count(func.distinct(base))
            elif fn == "AVG":
                if base is None:
                    continue
                expr = func.coalesce(func.avg(base), 0)
            elif fn == "MAX":
                if base is None:
                    continue
                expr = func.max(base)
            elif fn == "MIN":
                if base is None:
                    continue
                expr = func.min(base)
            else:  # SUM
                if base is None:
                    continue
                expr = func.coalesce(func.sum(base), 0)
            a_exprs.append(expr.label(f"a_{len(a_keys)}"))
            a_keys.append(sk)

        if not a_keys:
            return [], 0, None

        def _row_to_map(row: Any, *, with_groups: bool) -> dict[str, Any]:
            out: dict[str, Any] = {}
            idx = 0
            if with_groups:
                for sk in g_keys:
                    raw = row[idx]
                    idx += 1
                    if hasattr(raw, "isoformat"):
                        iso = raw.isoformat()
                        out[sk] = iso[:10] if "T" in iso or len(iso) >= 10 else iso
                    else:
                        out[sk] = "" if raw is None else raw
            for sk in a_keys:
                raw = row[idx]
                idx += 1
                try:
                    out[sk] = float(raw) if raw is not None else 0.0
                except (TypeError, ValueError):
                    out[sk] = 0.0
            return out

        base_where = [cls.tenant == ctx.tenant]
        grouped = select(*g_exprs, *a_exprs).where(*base_where).group_by(*g_exprs)
        grouped = self._apply_terms(grouped, terms)

        # stable order by group dims
        order_cols: list[Any] = []
        for i, g in enumerate(group_by):
            if i >= len(g_exprs):
                break
            if str(g.get("sort") or "ASC").upper() == "DESC":
                order_cols.append(desc(g_exprs[i]))
            else:
                order_cols.append(asc(g_exprs[i]))
        if order_cols:
            grouped = grouped.order_by(*order_cols)

        count_stmt = select(func.count()).select_from(grouped.order_by(None).subquery())
        group_count = int(session.scalar(count_stmt) or 0)

        rows = session.execute(
            grouped.offset((page - 1) * size).limit(size)
        ).all()
        values = [_row_to_map(r, with_groups=True) for r in rows]
        for i, row in enumerate(values):
            dims = [str(row.get(k) or "") for k in g_keys]
            row["$digest.uukey$"] = "|".join(dims) if dims else str(i + 1)
            row["id"] = (page - 1) * size + i + 1

        # grand totals (no group)
        tot_stmt = select(*a_exprs).where(*base_where)
        tot_stmt = self._apply_terms(tot_stmt, terms)
        tot_row = session.execute(tot_stmt).one_or_none()
        totals: dict[str, Any] | None = None
        if tot_row is not None:
            totals = _row_to_map(tot_row, with_groups=False)
            # 合计行：首个分组维放分组数（与普通列表 basic.uukey=count 同理）
            if g_keys:
                totals[g_keys[0]] = group_count

        return values, group_count, totals

    def _scoped_select(self, ctx: Ctx, terms: list[QueryTerm]) -> Any:
        cls = self.entity_cls
        stmt = select(cls).where(cls.tenant == ctx.tenant)
        # Soft-delete: hide deleted rows unless query explicitly filters basic.state
        if hasattr(cls, "state") and not any(
            t.field in ("basic.state", "basic.enable") for t in terms
        ):
            from modoor.core.state import STATE_ON

            stmt = stmt.where(cls.state == STATE_ON)
        return self._apply_terms(stmt, terms)

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
        cls = self.entity_cls
        page = max(int(page or 1), 1)
        size = min(max(int(size or 50), 1), 500)
        terms = parse_query(query)
        base = self._scoped_select(ctx, terms)
        count = session.scalar(select(func.count()).select_from(base.subquery())) or 0
        resolved = resolve_list_order(order)
        order_field = resolved["field"]
        order_dir = resolved["order"]
        col_name = self.COLS.get(order_field)
        col = getattr(cls, col_name, None) if col_name else None
        if col is None and order_field == "basic.utime":
            col = getattr(cls, "utime", None)
        if col is None:
            col = getattr(cls, self.COLS.get("basic.uukey", "uukey"), getattr(cls, "uukey", cls.id))
        ordered = base.order_by(desc(col) if order_dir == "desc" else asc(col))
        rows = session.scalars(ordered.offset((page - 1) * size).limit(size)).all()
        values = [self._to_values(r, field_keys) for r in rows]
        totals = self._search_totals(session, ctx, terms, field_keys, int(count))
        return values, int(count), totals

    def _named_col(self, source: Any, name: str | None) -> Any | None:
        if not name:
            return None
        if source is None:
            return getattr(self.entity_cls, name, None)
        try:
            return source.c[name]
        except AttributeError:
            return None

    def _value_expr(
        self,
        sk: str,
        *,
        as_date: bool = False,
        as_month: bool = False,
        source: Any = None,
    ) -> Any | None:
        """source 为空时读实体列；传入 CTE 时读同一次扫描的结果列。"""
        cls = self.entity_cls
        path = self._json_path(sk)
        if path:
            group, field = path
            if not hasattr(cls, group):
                return None
            col = getattr(cls, group) if source is None else source.c[group]
            text = col[field].as_string()
            if as_month:
                return func.nullif(func.left(text, 7), "")
            if as_date:
                return func.nullif(func.left(text, 10), "")
            if sk in self.NUM_KEYS:
                return self._json_number(col, field)
            return text
        attr = self.COLS.get(sk)
        if not attr or not hasattr(cls, attr):
            return None
        col = getattr(cls, attr) if source is None else source.c[attr]
        if as_month:
            # Postgres：YYYY-MM
            return func.to_char(col, "YYYY-MM")
        if as_date:
            return func.date(col)
        return col

    def enrich_search_totals(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        fields: list[dict[str, Any]],
        totals: dict[str, Any] | None,
        count: int,
    ) -> dict[str, Any] | None:
        """分类 / 日期字段：合计行填 distinct 个数（ONLYMONTH 按月，DATETIME 按日）。"""
        if count <= 0:
            return totals
        out = dict(totals or {})
        terms = parse_query(query)
        cls = self.entity_cls
        for f in fields:
            sk = str(f.get("uukey") or "").strip()
            if not sk or sk not in self.COLS:
                continue
            ft = str(f.get("ftype") or "").upper()
            if ft not in UNIQUE_TOTAL_TYPES or self._row_key(sk):
                continue
            extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
            data_type = str(extra.get("dataType") or extra.get("datetime") or "").upper()
            as_month = ft == "DATETIME" and data_type == "ONLYMONTH"
            as_date = ft == "DATETIME" and not as_month
            expr = self._value_expr(sk, as_date=as_date, as_month=as_month)
            if expr is None:
                continue
            stmt = select(func.count(func.distinct(expr))).where(cls.tenant == ctx.tenant)
            if not self._index_time(sk):
                stmt = stmt.where(expr.is_not(None))
            if not as_date and not as_month:
                stmt = stmt.where(expr != "")
            stmt = self._apply_terms(stmt, terms)
            try:
                n = session.execute(stmt).scalar()
                out[sk] = int(n or 0)
            except Exception:  # noqa: BLE001
                session.rollback()
                continue
        return out or None

    def search_facets(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        fields: list[dict[str, Any]],
        limit: int = 100,
    ) -> dict[str, Any] | None:
        """按当前 query 取普通字段 unique（≤limit 供表头下拉，否则 overflow）。"""
        lim = max(1, min(int(limit or 100), 500))
        terms = parse_query(query)
        cls = self.entity_cls
        out: dict[str, Any] = {}
        for f in fields:
            sk = str(f.get("uukey") or "").strip()
            if not sk or sk not in self.COLS:
                continue
            ft = str(f.get("ftype") or "").upper()
            if ft not in FACET_TYPES or self._index_time(sk) or self._row_key(sk):
                continue
            scoped = [t for t in terms if t.field != sk]
            extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
            data_type = str(extra.get("dataType") or extra.get("datetime") or "").upper()
            as_month = ft == "DATETIME" and data_type == "ONLYMONTH"
            as_date = ft == "DATETIME" and not as_month
            expr = self._value_expr(sk, as_date=as_date, as_month=as_month)
            if expr is None:
                continue
            stmt = select(expr).where(cls.tenant == ctx.tenant).distinct().limit(lim + 1)
            if not self._index_time(sk):
                stmt = stmt.where(expr.is_not(None))
            if not as_date and not as_month:
                stmt = stmt.where(expr != "")
            stmt = self._apply_terms(stmt, scoped)
            try:
                rows = session.execute(stmt).all()
            except Exception:  # noqa: BLE001
                session.rollback()
                continue
            vals: list[str] = []
            for (raw,) in rows:
                if raw is None:
                    continue
                if hasattr(raw, "isoformat"):
                    iso = raw.isoformat()
                    s = iso[:7] if as_month else (iso[:10] if as_date else iso)
                else:
                    s = str(raw).strip()
                    if as_month and len(s) >= 7:
                        s = s[:7]
                    elif as_date and len(s) >= 10:
                        s = s[:10]
                if s:
                    vals.append(s)
            uniq: list[str] = []
            seen: set[str] = set()
            for s in vals:
                if s in seen:
                    continue
                seen.add(s)
                uniq.append(s)
            if len(uniq) > lim:
                out[sk] = {"overflow": True}
            else:
                uniq.sort()
                out[sk] = {
                    "overflow": False,
                    "options": [{"value": v, "label": v} for v in uniq],
                }
        return out or None

    def _search_totals(
        self,
        session: Session,
        ctx: Ctx,
        terms: list[QueryTerm],
        field_keys: list[str],
        count: int,
    ) -> dict[str, Any] | None:
        """SUM NUMERIC（含 JSON 组内数值列）。"""
        if count <= 0:
            return None
        totals: dict[str, Any] = {}
        if "basic.uukey" in field_keys:
            totals["basic.uukey"] = count

        cls = self.entity_cls
        used_keys: list[str] = []
        aggs: list[Any] = []
        for sk in field_keys:
            if sk not in self.NUM_KEYS or sk not in self.COLS:
                continue
            path = self._json_path(sk)
            if path:
                group, field = path
                if not hasattr(cls, group):
                    continue
                expr = func.coalesce(func.sum(self._json_num_expr(group, field)), 0)
            else:
                attr = self.COLS[sk]
                if not hasattr(cls, attr):
                    continue
                expr = func.coalesce(func.sum(getattr(cls, attr)), 0)
            used_keys.append(sk)
            aggs.append(expr.label(sk.replace(".", "_")))

        if aggs:
            stmt = select(*aggs).where(cls.tenant == ctx.tenant)
            stmt = self._apply_terms(stmt, terms)
            row = session.execute(stmt).one()
            for i, sk in enumerate(used_keys):
                raw = row[i]
                try:
                    totals[sk] = float(raw) if raw is not None else 0.0
                except (TypeError, ValueError):
                    totals[sk] = 0.0

        return totals or None

    def search_report(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        order: dict[str, Any] | None,
        page: int,
        size: int,
        field_keys: list[str],
        fields: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None, dict[str, Any] | None]:
        """一次取出本页、条数、合计和筛选项。条件相同的统计共用一次扫描。"""
        page = max(int(page or 1), 1)
        size = min(max(int(size or 50), 1), 500)
        terms = parse_query(query)
        lim = 100
        stat_fields = self._stat_fields(fields)
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for spec in stat_fields:
            if not spec["facet"]:
                continue
            scoped = [t for t in terms if t.field != spec["sk"]]
            spec["scoped"] = scoped
            groups.setdefault(self._term_signature(scoped), []).append(spec)

        full_sig = self._term_signature(terms)
        same_where = groups.pop(full_sig, [])
        pending = groups
        scan_terms = list(terms)
        narrow_terms: list[QueryTerm] = []

        columns: list[Any] = [self._count_agg(narrow_terms).label("n")]
        sum_keys: list[str] = []
        distinct_keys: list[str] = []
        facet_slots: list[dict[str, Any]] = []
        for sk in field_keys:
            if sk not in self.NUM_KEYS or sk not in self.COLS:
                continue
            expr = self._value_expr(sk)
            if expr is None:
                continue
            columns.append(self._sum_agg(expr, narrow_terms).label(f"sum_{len(sum_keys)}"))
            sum_keys.append(sk)
        for spec in stat_fields:
            if not spec["unique"]:
                continue
            agg = self._distinct_count_agg(spec, narrow_terms)
            if agg is None:
                continue
            columns.append(agg.label(f"unq_{len(distinct_keys)}"))
            distinct_keys.append(spec["sk"])
        for spec in same_where:
            agg = self._facet_agg(spec, narrow_terms)
            if agg is None:
                continue
            columns.append(agg.label(f"fac_{len(facet_slots)}"))
            facet_slots.append(spec)

        where = self._scoped_select(ctx, scan_terms).whereclause
        row = session.execute(select(*columns).where(where)).one()
        count = int(row[0] or 0)
        cursor = 1
        totals: dict[str, Any] | None = None
        if count > 0:
            totals = {}
            if "basic.uukey" in field_keys:
                totals["basic.uukey"] = count
            for sk in sum_keys:
                raw = row[cursor]
                cursor += 1
                try:
                    totals[sk] = float(raw) if raw is not None else 0.0
                except (TypeError, ValueError):
                    totals[sk] = 0.0
            for sk in distinct_keys:
                totals[sk] = int(row[cursor] or 0)
                cursor += 1
        else:
            cursor += len(sum_keys) + len(distinct_keys)

        facets: dict[str, Any] = {}
        for spec in facet_slots:
            facets[spec["sk"]] = self._facet_payload(row[cursor], spec, lim)
            cursor += 1

        for specs in pending.values():
            scoped = specs[0]["scoped"]
            extra_cols: list[Any] = []
            extra_specs: list[dict[str, Any]] = []
            for spec in specs:
                agg = self._facet_agg(spec, [])
                if agg is None:
                    continue
                extra_cols.append(agg.label(f"x_{len(extra_specs)}"))
                extra_specs.append(spec)
            if not extra_cols:
                continue
            extra = session.execute(
                select(*extra_cols).where(self._scoped_select(ctx, scoped).whereclause)
            ).one()
            for index, spec in enumerate(extra_specs):
                facets[spec["sk"]] = self._facet_payload(extra[index], spec, lim)

        order_col, order_fn = self._order_piece(None, order)
        rows = session.scalars(
            self._scoped_select(ctx, terms)
            .order_by(order_fn(order_col))
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        values = [self._to_values(item, field_keys) for item in rows]
        return values, count, totals or None, facets or None

    def _stat_fields(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for field in fields:
            sk = str(field.get("uukey") or "").strip()
            if not sk or sk not in self.COLS:
                continue
            ftype = str(field.get("ftype") or "").upper()
            extra = field.get("extra") if isinstance(field.get("extra"), dict) else {}
            data_type = str(extra.get("dataType") or extra.get("datetime") or "").upper()
            as_month = ftype == "DATETIME" and data_type == "ONLYMONTH"
            specs.append(
                {
                    "sk": sk,
                    "as_month": as_month,
                    "as_date": ftype == "DATETIME" and not as_month,
                    "unique": ftype in UNIQUE_TOTAL_TYPES and not self._row_key(sk),
                    "facet": ftype in FACET_TYPES and not self._index_time(sk) and not self._row_key(sk),
                }
            )
        return specs

    def _term_id(self, term: QueryTerm) -> tuple:
        return (term.field, term.op, str(term.group or ""), repr(term.value))

    def _term_signature(self, terms: list[QueryTerm]) -> tuple:
        return tuple(self._term_id(term) for term in terms)

    def _count_agg(self, scope_terms: list[QueryTerm]) -> Any:
        agg = func.count()
        clause = self._terms_clause(scope_terms)
        if clause is None:
            return agg
        return agg.filter(clause)

    def _sum_agg(self, expr: Any, scope_terms: list[QueryTerm]) -> Any:
        agg = func.sum(expr)
        clause = self._terms_clause(scope_terms)
        if clause is not None:
            agg = agg.filter(clause)
        return func.coalesce(agg, 0)

    def _order_piece(self, source: Any, order: dict[str, Any] | None) -> tuple[Any, Any]:
        resolved = resolve_list_order(order)
        name = self.COLS.get(resolved["field"])
        col = self._named_col(source, name)
        if col is None and resolved["field"] == "basic.utime":
            col = self._named_col(source, "utime")
        if col is None:
            col = self._named_col(source, self.COLS.get("basic.uukey", "uukey"))
        if col is None:
            col = self._named_col(source, "id")
        return col, desc if resolved["order"] == "desc" else asc

    def _stat_expr(self, spec: dict[str, Any]) -> Any | None:
        if not spec["as_date"] and not spec["as_month"] and not self._plain_text(spec["sk"]):
            return None
        return self._value_expr(spec["sk"], as_date=spec["as_date"], as_month=spec["as_month"])

    def _plain_text(self, sk: str) -> bool:
        """JSON 数组没有和空字符串比较、也没有 DISTINCT 的运算符。"""
        if self._json_path(sk):
            return True
        if sk in self.LIST_KEYS:
            return False
        attr = self.COLS.get(sk)
        col = getattr(self.entity_cls, attr, None) if attr else None
        typ = getattr(col, "type", None)
        return not isinstance(typ, JSON)

    def _index_time(self, sk: str) -> bool:
        """列名 utime 与 created_at、updated_at、user_id 一样是约定字段，统计时按非空处理。"""
        return self.COLS.get(sk) == "utime"

    def _row_key(self, sk: str) -> bool:
        """列名 uukey 是约定的业务编号，每行唯一，不做去重和下拉。"""
        return self.COLS.get(sk) == "uukey"

    def _present(self, expr: Any, spec: dict[str, Any]) -> Any | None:
        if self._index_time(spec["sk"]):
            return None
        cond = expr.is_not(None)
        if spec["as_date"] or spec["as_month"]:
            return cond
        return and_(cond, expr != "")

    def _with_present(
        self,
        agg: Any,
        expr: Any,
        spec: dict[str, Any],
        scope_terms: list[QueryTerm] | None = None,
    ) -> Any:
        parts: list[Any] = []
        present = self._present(expr, spec)
        if present is not None:
            parts.append(present)
        clause = self._terms_clause(scope_terms or [])
        if clause is not None:
            parts.append(clause)
        if not parts:
            return agg
        return agg.filter(and_(*parts) if len(parts) > 1 else parts[0])

    def _distinct_count_agg(
        self,
        spec: dict[str, Any],
        scope_terms: list[QueryTerm] | None = None,
    ) -> Any | None:
        expr = self._stat_expr(spec)
        if expr is None:
            return None
        return self._with_present(func.count(distinct(expr)), expr, spec, scope_terms)

    def _facet_agg(
        self,
        spec: dict[str, Any],
        scope_terms: list[QueryTerm] | None = None,
    ) -> Any | None:
        expr = self._stat_expr(spec)
        if expr is None:
            return None
        return self._with_present(func.array_agg(distinct(expr)), expr, spec, scope_terms)

    def _facet_payload(self, raw: Any, spec: dict[str, Any], lim: int) -> dict[str, Any]:
        uniq: list[str] = []
        seen: set[str] = set()
        for item in raw or []:
            text = self._facet_text(item, as_month=spec["as_month"], as_date=spec["as_date"])
            if not text or text in seen:
                continue
            seen.add(text)
            uniq.append(text)
        if len(uniq) > lim:
            return {"overflow": True}
        uniq.sort()
        return {"overflow": False, "options": [{"value": v, "label": v} for v in uniq]}

    @staticmethod
    def _facet_text(raw: Any, *, as_month: bool, as_date: bool) -> str:
        if raw is None:
            return ""
        if hasattr(raw, "isoformat"):
            iso = raw.isoformat()
            if as_month:
                return iso[:7]
            if as_date:
                return iso[:10]
            return iso
        text = str(raw).strip()
        if as_month and len(text) >= 7:
            return text[:7]
        if as_date and len(text) >= 10:
            return text[:10]
        return text

    def get_values(self, session: Session, ctx: Ctx, uukey: str) -> dict[str, Any] | None:
        row = self._resolve(session, ctx, uukey)
        if row is None:
            return None
        return self._to_values(row)

    def _coerce_num(self, sk: str, val: Any) -> Any:
        """Hook for module-specific numeric coerce (e.g. uterm)."""
        d = to_dec(val)
        return to_float(d) if self._json_path(sk) else d

    def _list_has_any(self, col: Any, values: list[Any]) -> Any | None:
        wanted = [str(v).strip() for v in values if str(v).strip()]
        if not wanted:
            return None
        blob = cast(col, JSONB)
        clauses = [blob.contains([item]) for item in wanted]
        return or_(*clauses) if len(clauses) > 1 else clauses[0]

    def _list_clause(self, col: Any, op: str, val: Any) -> Any | None:
        """多选标签存在 JSON 数组里：命中其中一项即可。"""
        if op in ("IN", "EQ"):
            vals = val if isinstance(val, list) else [val]
            return self._list_has_any(col, vals)
        if op == "NE":
            hit = self._list_has_any(col, [val])
            if hit is None:
                return None
            # 没打标签的也算「不包含」，否则 NULL 会被 NOT 滤掉
            return or_(col.is_(None), ~hit)
        if op == "NIL":
            text = cast(col, String)
            empty = or_(col.is_(None), text.in_(["[]", "null", ""]))
            return empty if val in (True, "true", 1, "1") else ~empty
        if op == "LIKE":
            return cast(col, String).ilike(f"%{val}%")
        return None

    def _coerce_list(self, val: Any) -> list[str]:
        if val in (None, ""):
            return []
        if isinstance(val, list):
            return [str(item).strip() for item in val if str(item).strip()]
        text = str(val).strip()
        if not text:
            return []
        return [part.strip() for part in text.replace(",", "\n").split("\n") if part.strip()]

    def _coerce_write(self, sk: str, val: Any) -> Any:
        if sk in self.LIST_KEYS:
            return self._coerce_list(val)
        if val in (None, ""):
            return None if sk in self.DT_KEYS or sk in self.NUM_KEYS else ""
        if sk in self.DT_KEYS:
            d = parse_dt(val)
            return to_iso(d) if self._json_path(sk) else d
        if sk in self.NUM_KEYS:
            return self._coerce_num(sk, val)
        return str(val).strip() if isinstance(val, str) else val

    def _before_write(
        self,
        session: Session,
        ctx: Ctx,
        entity: Any,
        row: dict[str, Any],
        *,
        is_update: bool,
    ) -> None:
        """Hook before columns are overwritten. Use it to remember the previous term or driver."""
        _ = (session, ctx, entity, row, is_update)

    def _finalize_entity(
        self,
        session: Session,
        ctx: Ctx,
        entity: Any,
        row: dict[str, Any],
        *,
        is_update: bool,
    ) -> None:
        """Hook after columns written (uterm sync, etc.)."""
        _ = (session, ctx, entity, row, is_update)

    def upsert(
        self,
        session: Session,
        ctx: Ctx,
        batch: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from modoor.engine.oplog import diff_row_values, record_oplog

        cls = self.entity_cls
        records: list[dict[str, Any]] = []
        for raw in batch:
            row = normalize_batch_row(raw)
            code = str(row.get("basic.uukey") or row.get("uukey") or "").strip()
            existing = self._resolve(session, ctx, code) if code else None
            is_update = existing is not None
            entity = existing if is_update else None
            before = self._to_values(existing) if is_update and existing is not None else None
            if not is_update:
                for req in self.REQUIRED_ON_CREATE:
                    if not str(flatten_pick(row, req) or "").strip():
                        raise AppError("validation_error", f"{req} is required")
                biz = code or self._alloc_uukey(session, ctx)
                entity = cls(
                    id=str(uuid.uuid4()),
                    tenant=ctx.tenant,
                    uukey=biz,
                )
                session.add(entity)

            assert entity is not None
            self._before_write(session, ctx, entity, row, is_update=is_update)
            json_patch: dict[str, dict[str, Any]] = {}
            for sk, attr in self.COLS.items():
                if sk == "basic.uukey":
                    continue
                path = self._json_path(sk)
                if path:
                    group, field = path
                    if sk not in row and not (
                        isinstance(row.get(group), dict) and field in row[group]
                    ):
                        continue
                    val = flatten_pick(row, sk)
                    json_patch.setdefault(group, {})[field] = self._coerce_write(sk, val)
                    continue
                if sk not in row:
                    continue
                val = flatten_pick(row, sk)
                setattr(entity, attr, self._coerce_write(sk, val))

            for group, patch in json_patch.items():
                cur = dict(getattr(entity, group, None) or {})
                cur.update(patch)
                setattr(entity, group, cur)

            self._normalize_fks(session, ctx, entity)
            self._finalize_entity(session, ctx, entity, row, is_update=is_update)

            if self.after_upsert:
                self.after_upsert(session, ctx, entity, row, is_update)

            session.flush()
            current = self._to_values(entity)
            changes = diff_row_values(before, current)
            changed = bool(changes) if is_update else True
            if self.AUDIT_OPLOG and changed:
                record_oplog(
                    session,
                    ctx,
                    code=self._biz_code(entity),
                    action="UPDATE" if is_update else "INSERT",
                    model=self.model,
                    before=before,
                    after=current,
                    diff=changes,
                )
            records.append(
                {
                    "uukey": self._biz_code(entity),
                    "model": self.model,
                    "opType": "UPDATE" if is_update else "INSERT",
                    "exists": is_update,
                    "request": row,
                    "current": current,
                    "prepare": current,
                    "storage": {"basic": current},
                    "changed": changed,
                    "changes": changes,
                    "objects": None,
                }
            )
        return records

    def delete_keys(self, session: Session, ctx: Ctx, keys: list[str]) -> None:
        from modoor.core.state import STATE_OFF
        from modoor.engine.oplog import record_oplog

        for key in keys:
            row = self._resolve(session, ctx, key)
            if row is None:
                continue
            before = self._to_values(row) if self.AUDIT_OPLOG else None
            code = self._biz_code(row)
            if hasattr(row, "state"):
                row.state = STATE_OFF
            else:
                session.delete(row)
            if self.AUDIT_OPLOG and before is not None:
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

    def alloc_serials(
        self,
        session: Session,
        ctx: Ctx,
        count: int,
        kind: str | None = None,
    ) -> list[str]:
        _ = kind
        n = max(0, min(int(count or 0), 100))
        if n <= 0:
            return []
        prefix, width = self._serial_meta()
        first = self._alloc_uukey(session, ctx)
        p = (prefix or "X").strip().upper() or "X"
        w = max(1, int(width or 5))
        try:
            start = int(str(first)[len(p) :])
        except ValueError:
            return [first] + [""] * (n - 1)
        return [f"{p}{start + i:0{w}d}" for i in range(n)]
