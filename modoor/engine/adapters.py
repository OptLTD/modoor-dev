"""Model adapters: schema index ↔ domain ORM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError


class ModelAdapter(ABC):
    model: str

    @abstractmethod
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
        """Return values, count, totals."""

    def search_facets(
        self,
        session: Session,
        ctx: Ctx,
        *,
        query: dict[str, Any] | None,
        fields: list[dict[str, Any]],
        limit: int = 100,
    ) -> dict[str, Any] | None:
        """Optional: distinct values for header filters. Default: none."""
        return None

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
        """Optional: enrich totals (e.g. RELATION distinct). Default: passthrough."""
        _ = (session, ctx, query, fields, count)
        return totals

    @abstractmethod
    def get_values(self, session: Session, ctx: Ctx, uukey: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def upsert(
        self,
        session: Session,
        ctx: Ctx,
        batch: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def delete_keys(self, session: Session, ctx: Ctx, keys: list[str]) -> None:
        ...

    def refers(self, session: Session, ctx: Ctx) -> dict[str, Any]:
        """Optional lookup dicts for OPTIONAL/RELATION fields."""
        return {}

    def alloc_serials(
        self,
        session: Session,
        ctx: Ctx,
        count: int,
        kind: str | None = None,
    ) -> list[str]:
        """Reserve consecutive business serials (no row insert). Default: empty placeholders."""
        n = max(0, min(int(count or 0), 100))
        return [""] * n

    def autofill(
        self,
        session: Session,
        ctx: Ctx,
        row: dict[str, Any],
        *,
        fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Optional hook after formula eval. Return updated flat row (may mutate a copy)."""
        _ = (session, ctx, fields)
        return row

    def hook(self, session: Session, ctx: Ctx, payload: dict[str, Any]) -> dict[str, Any]:
        """Optional: adjust schema and/or result rows before the response is returned."""
        _ = (session, ctx)
        return payload


_ADAPTERS: dict[str, ModelAdapter] = {}


def register_adapter(adapter: ModelAdapter) -> None:
    _ADAPTERS[adapter.model] = adapter


def get_adapter(model: str) -> ModelAdapter:
    if model not in _ADAPTERS:
        from modoor.platform.loader import register_module_adapters

        register_module_adapters()
    if model not in _ADAPTERS:
        raise AppError("not_found", f"no adapter for model: {model}")
    return _ADAPTERS[model]


def flatten_pick(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    if "." in key:
        group, field = key.split(".", 1)
        nested = row.get(group)
        if isinstance(nested, dict) and field in nested:
            return nested[field]
        if field in row:
            return row[field]
    return None


def normalize_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    """Prefer group.field keys; keep bare basic.* aliases collapsed."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in {"uukey", "model", "logid"}:
            out[k] = v
            continue
        if "." in k:
            out[k] = v
        else:
            # bare field — only fill if flat missing
            flat = f"basic.{k}"
            out.setdefault(flat, v)
    if "basic.uukey" not in out and row.get("uukey"):
        out["basic.uukey"] = row["uukey"]
    if "basic.code" not in out and row.get("code"):
        out["basic.code"] = row["code"]
    if "basic.code" not in out and out.get("basic.uukey"):
        # legacy uukey payload for base.user
        pass
    return out
