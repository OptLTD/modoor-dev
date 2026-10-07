"""EngineService — TableSchema / Search / Input / Upsert (worth wire)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.engine.adapters import get_adapter
from modoor.engine.formula import apply_formulas, ensure_fields_depends
from modoor.engine.project import build_source, merge_dict_key_refers, project_input, project_table
from modoor.engine.registry import clear_bundle_cache, get_bundle, login_tabs


class EngineService:
    def table_schema(
        self,
        session: Session,
        ctx: Ctx,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        model = str(body.get("model") or "").strip()
        if not model:
            raise AppError("validation_error", "model required")
        using = str(body.get("using") or "default")
        scene = str(body.get("scene") or "SEARCH")
        page = int(body.get("page") or 1)
        size = int(body.get("size") or 50)
        bundle = get_bundle(model)
        table = project_table(
            bundle,
            using=using,
            scene=scene,
            page=page,
            size=size,
            query=body.get("query") if isinstance(body.get("query"), dict) else None,
            order=body.get("order") if isinstance(body.get("order"), dict) else None,
        )
        table["fields"] = ensure_fields_depends(list(table.get("fields") or []))
        adapter = get_adapter(model)
        refers = dict(table.get("refers") or {})
        refers.update(adapter.refers(session, ctx) or {})
        refers = merge_dict_key_refers(session, ctx, list(table.get("fields") or []), refers)
        table["refers"] = refers
        payload: dict[str, Any] = {
            "model": model,
            "using": using,
            "scene": scene,
            "table": table,
            "source": build_source(bundle),
        }
        tabs = login_tabs(model)
        if tabs:
            payload["tabs"] = tabs
        return adapter.hook(session, ctx, payload)

    def input_schema(
        self,
        session: Session,
        ctx: Ctx,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        model = str(body.get("model") or "").strip()
        if not model:
            raise AppError("validation_error", "model required")
        using = str(body.get("using") or "default")
        uukey = str(body.get("uukey") or "").strip()
        scene = str(body.get("scene") or ("DETAIL" if uukey else "INSERT"))
        bundle = get_bundle(model)
        inp = project_input(bundle, using=using, scene=scene, uukey=uukey)
        inp["fields"] = ensure_fields_depends(list(inp.get("fields") or []))
        adapter = get_adapter(model)
        refers = dict(inp.get("refers") or {})
        refers.update(adapter.refers(session, ctx) or {})
        refers = merge_dict_key_refers(session, ctx, list(inp.get("fields") or []), refers)
        inp["refers"] = refers
        if uukey:
            values = adapter.get_values(session, ctx, uukey)
            if values is None:
                raise AppError("not_found", f"record not found: {uukey}")
            # merge preset under real values
            merged = dict(inp.get("values") or {})
            merged.update(values)
            inp["values"] = merged
        return adapter.hook(
            session,
            ctx,
            {
                "model": model,
                "using": using,
                "scene": scene,
                "input": inp,
            },
        )

    def autofill(
        self,
        session: Session,
        ctx: Ctx,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        model = str(body.get("model") or "").strip()
        if not model:
            raise AppError("validation_error", "model required")
        using = str(body.get("using") or "default")
        bundle = get_bundle(model)
        inp = project_input(bundle, using=using, scene="INSERT")
        fields = ensure_fields_depends(list(inp.get("fields") or []))
        adapter = get_adapter(model)

        def _one(row: dict[str, Any]) -> dict[str, Any]:
            filled = apply_formulas(fields, row)
            try:
                hooked = adapter.autofill(session, ctx, filled, fields=fields)
            except Exception as exc:  # noqa: BLE001
                raise AppError("validation_error", f"autofill failed: {exc}") from exc
            return hooked if isinstance(hooked, dict) else filled

        batch = body.get("batch")
        if isinstance(batch, list):
            data = [_one(row if isinstance(row, dict) else {}) for row in batch]
            return {"data": data}
        value = body.get("value") if isinstance(body.get("value"), dict) else {}
        return {"data": _one(value)}

    def search(
        self,
        session: Session,
        ctx: Ctx,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        model = str(body.get("model") or "").strip()
        if not model:
            raise AppError("validation_error", "model required")
        using = str(body.get("using") or "default")
        scene = str(body.get("scene") or "SEARCH")
        page = int(body.get("page") or 1)
        size = int(body.get("size") or 50)
        bundle = get_bundle(model)
        table = project_table(
            bundle,
            using=using,
            scene=scene,
            page=page,
            size=size,
            query=body.get("query") if isinstance(body.get("query"), dict) else None,
            order=body.get("order") if isinstance(body.get("order"), dict) else None,
        )
        req = table["request"]
        # request query already merged view defaults with caller in project_table;
        # re-apply body query with field-aware merge for safety.
        from modoor.engine.query import merge_search_query

        query = merge_search_query(
            dict(req.get("query") or {}),
            body.get("query") if isinstance(body.get("query"), dict) else None,
        )
        order = body.get("order") if isinstance(body.get("order"), dict) else req.get("order")
        field_keys = [f["uukey"] for f in table["fields"]]
        adapter = get_adapter(model)

        others = table.get("others") if isinstance(table.get("others"), dict) else {}
        digest_meta = others.get("$digest") if isinstance(others.get("$digest"), dict) else None
        if digest_meta and hasattr(adapter, "digest"):
            values, count, totals = adapter.digest(
                session,
                ctx,
                query=query,
                group_by=list(digest_meta.get("group_by") or []),
                count_fn=list(digest_meta.get("count_fn") or []),
                page=page,
                size=size,
            )
            fields = list(table.get("fields") or [])
            from modoor.engine.digest import recalc_digest_rows

            totals = recalc_digest_rows(fields, values, totals)
            refers = dict(table.get("refers") or {})
            refers.update(adapter.refers(session, ctx) or {})
            refers = merge_dict_key_refers(session, ctx, fields, refers)
            return adapter.hook(
                session,
                ctx,
                {
                    "page": page,
                    "size": size,
                    "count": count,
                    "using": using,
                    "facets": None,
                    "refers": refers,
                    "totals": totals,
                    "values": values,
                },
            )

        values, count, totals = adapter.search(
            session, ctx,
            query=query,
            order=order,
            page=page,
            size=size,
            field_keys=field_keys,
        )
        fields = list(table.get("fields") or [])
        totals = adapter.enrich_search_totals(
            session, ctx,
            query=query,
            fields=fields,
            totals=totals,
            count=int(count),
        )
        facets = adapter.search_facets(
            session, ctx,
            query=query,
            fields=fields,
            limit=100,
        )
        refers = dict(table.get("refers") or {})
        refers.update(adapter.refers(session, ctx) or {})
        refers = merge_dict_key_refers(session, ctx, fields, refers)
        return adapter.hook(
            session,
            ctx,
            {
                "using": using,
                "page": page,
                "size": size,
                "count": count,
                "refers": refers,
                "totals": totals,
                "facets": facets,
                "values": values,
            },
        )

    def upsert(
        self,
        session: Session,
        ctx: Ctx,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        model = str(body.get("model") or "").strip()
        if not model:
            raise AppError("validation_error", "model required")
        batch = body.get("batch")
        if not isinstance(batch, list) or not batch:
            raise AppError("validation_error", "batch required")
        # validate model exists
        get_bundle(model)
        adapter = get_adapter(model)
        records = adapter.upsert(session, ctx, batch)
        _stamp_upload_assets(session, ctx, model, records)
        return {"records": records}

    def delete(
        self,
        session: Session,
        ctx: Ctx,
        *,
        model: str,
        keys: list[str],
    ) -> dict[str, Any]:
        get_bundle(model)
        adapter = get_adapter(model)
        adapter.delete_keys(session, ctx, keys)
        return {"ok": True}

    def alloc_serials(
        self,
        session: Session,
        ctx: Ctx,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        model = str(body.get("model") or "").strip()
        if not model:
            raise AppError("validation_error", "model required")
        count = int(body.get("count") or 0)
        kind = body.get("kind")
        kind_s = str(kind).strip() if kind not in (None, "") else None
        get_bundle(model)
        adapter = get_adapter(model)
        codes = adapter.alloc_serials(session, ctx, count, kind_s)
        return {"codes": list(codes or [])}


def _asset_ids(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item or "").strip()]
    text = str(raw).strip()
    return [text] if text else []


def _record_values(rec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    current = rec.get("current")
    if isinstance(current, dict):
        uukey = str(rec.get("uukey") or current.get("basic.uukey") or "").strip()
        return uukey, current
    uukey = str(rec.get("basic.uukey") or rec.get("uukey") or "").strip()
    return uukey, rec


def _stamp_upload_assets(
    session: Session,
    ctx: Ctx,
    model: str,
    records: list[Any],
) -> None:
    """记录写入成功后，把附件标上 model、uukey、字段键。一份文件只属于一条记录。"""
    bundle = get_bundle(model)
    upload_keys = [
        key
        for key, spec in (bundle.fields or {}).items()
        if str((spec or {}).get("ftype") or "").upper() == "UPLOADS"
    ]
    if not upload_keys:
        return
    from builtin.doc import domain as doc_domain

    for rec in records:
        if not isinstance(rec, dict):
            continue
        uukey, values = _record_values(rec)
        if not uukey:
            continue
        present = [key for key in upload_keys if key in values]
        if not present:
            continue
        owned: dict[str, str] = {}
        for key in present:
            for asset_id in _asset_ids(values.get(key)):
                owned[asset_id] = key
        doc_domain.sync_record_assets(
            session,
            ctx,
            model=model,
            uukey=uukey,
            owned=owned,
            fields=present,
        )


@lru_cache
def get_engine() -> EngineService:
    return EngineService()


def reload_engine_caches() -> None:
    clear_bundle_cache()
    get_engine.cache_clear()
