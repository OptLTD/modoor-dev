"""Doc domain — unstructured asset warehouse for AI + human preview."""

from __future__ import annotations

import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError
from modoor.runtime.jobs import enqueue
from builtin.doc.extract import MAX_TEXT_CHARS as _MAX_TEXT_CHARS
from builtin.doc.extract import sanitize_pg_text
from builtin.doc.jobs import register as register_extract_jobs
from builtin.doc.settings import get_doc_settings
from builtin.doc.storage import BlobStore, get_blob_store

register_extract_jobs()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _safe_filename(name: str) -> str:
    base = Path(name or "file").name
    cleaned = re.sub(r"[^\w.\-()+ ]+", "_", base, flags=re.UNICODE).strip("._ ")
    return (cleaned or "file")[:180]


def _guess_mime(filename: str, declared: str | None = None) -> str:
    if declared and declared.strip() and declared != "application/octet-stream":
        return declared.strip()
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _dumps_tags(tags: list[str] | None) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        t = str(raw or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        cleaned.append(t[:64])
    return json.dumps(cleaned, ensure_ascii=False)


def _loads_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


class DocAsset(Base):
    __tablename__ = "doc_asset"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(512))
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(String(32), default="local")  # storage backend
    name: Mapped[str] = mapped_column(String(1024), default="")  # object key
    tags: Mapped[str] = mapped_column(Text, default="[]")
    # 一份文件只属于一条记录的一个字段。field 存字段键，例如 files.id_card。
    model: Mapped[str] = mapped_column(String(128), default="", server_default="", index=True)
    uukey: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    field: Mapped[str] = mapped_column(String(128), default="", server_default="")
    text: Mapped[str] = mapped_column(Text, default="")
    text_status: Mapped[str] = mapped_column(String(16), default="pending")
    text_method: Mapped[str] = mapped_column(String(64), default="")
    text_error: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


def _asset_dict(row: DocAsset, *, include_text: bool = True, text_limit: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "tenant": row.tenant,
        "team_id": row.team_id,
        "title": row.title,
        "filename": row.filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "type": row.type,
        "name": row.name,
        "tags": _loads_tags(row.tags),
        "model": row.model or "",
        "uukey": row.uukey or "",
        "field": row.field or "",
        "note": row.note or "",
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "has_text": bool((row.text or "").strip()),
        "text_status": row.text_status or "ready",
        "text_method": row.text_method or "",
        "text_error": row.text_error or "",
        "ext": Path(row.filename or "").suffix.lower().lstrip("."),
    }
    if include_text:
        body = row.text or ""
        if text_limit is not None and len(body) > text_limit:
            data["text"] = body[:text_limit]
            data["text_truncated"] = True
        else:
            data["text"] = body
            data["text_truncated"] = False
    return data


def _scope(ctx: Ctx):
    return select(DocAsset).where(DocAsset.tenant == ctx.tenant)


def _get_asset(session: Session, ctx: Ctx, asset_id: str) -> DocAsset:
    row = session.get(DocAsset, asset_id)
    if row is None or row.tenant != ctx.tenant:
        raise AppError("not_found", "Doc asset not found")
    return row


def _store_for_row(row: DocAsset, settings=None) -> BlobStore:
    """Use current configured store; type on row is a snapshot for future multi-backend reads."""
    settings = settings or get_doc_settings()
    store = get_blob_store(settings)
    # If row was written with another backend, refuse silent mismatch for now
    if row.type and row.type != store.backend:
        raise AppError(
            "not_implemented",
            f"asset stored on '{row.type}' but current MODOOR_DOC_STORAGE is '{store.backend}'",
        )
    return store


def create_asset(
    session: Session,
    ctx: Ctx,
    *,
    filename: str,
    data: bytes,
    title: str | None = None,
    mime_type: str | None = None,
    tags: list[str] | None = None,
    note: str = "",
    text: str | None = None,
    model: str = "",
    uukey: str = "",
    field: str = "",
) -> dict[str, Any]:
    if not data and text is None:
        raise AppError("validation_error", "file content is required")
    settings = get_doc_settings()
    store = get_blob_store(settings)
    asset_id = _new_id()
    safe = _safe_filename(filename or "file")
    mime = _guess_mime(safe, mime_type)
    blob = data if data else (text or "").encode("utf-8")
    object_name = f"{ctx.tenant}/{asset_id}/{safe}"
    store.put(object_name, blob, content_type=mime)
    provided = text is not None
    row = DocAsset(
        id=asset_id,
        tenant=ctx.tenant,
        team_id=ctx.team_id,
        title=(title or Path(safe).stem or "Untitled").strip()[:512],
        filename=safe,
        mime_type=mime,
        size_bytes=len(blob),
        type=store.backend,
        name=object_name,
        tags=_dumps_tags(tags),
        model=(model or "").strip()[:128],
        uukey=(uukey or "").strip()[:64],
        field=(field or "").strip()[:128],
        text=sanitize_pg_text(text or "")[:_MAX_TEXT_CHARS] if provided else "",
        text_status="ready" if provided else "pending",
        text_method="provided" if provided else "",
        text_error="",
        note=sanitize_pg_text((note or "").strip()),
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    session.add(row)
    session.flush()
    if not provided:
        enqueue(session, kind="doc.extract", payload={"asset_id": asset_id})
    return _asset_dict(row)


def create_text_asset(
    session: Session,
    ctx: Ctx,
    *,
    title: str,
    text: str,
    tags: list[str] | None = None,
    note: str = "",
    filename: str | None = None,
    model: str = "",
    uukey: str = "",
    field: str = "",
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise AppError("validation_error", "title is required")
    body = text or ""
    fname = _safe_filename(filename or f"{title}.txt")
    return create_asset(
        session,
        ctx,
        filename=fname,
        data=body.encode("utf-8"),
        title=title,
        mime_type="text/plain; charset=utf-8",
        tags=tags,
        note=note,
        text=body,
        model=model,
        uukey=uukey,
        field=field,
    )


def list_assets(
    session: Session,
    ctx: Ctx,
    *,
    q: str | None = None,
    tag: str | None = None,
    model: str | None = None,
    tag_empty: bool = False,
    model_empty: bool = False,
    uukey: str | None = None,
    field: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    limit = min(max(int(limit or 100), 1), 500)
    rows = list(session.scalars(_scope(ctx).order_by(DocAsset.updated_at.desc())))
    needle = (q or "").strip().lower()
    tag_needle = (tag or "").strip()
    model_needle = (model or "").strip()
    uukey_needle = (uukey or "").strip()
    field_needle = (field or "").strip()
    items: list[dict[str, Any]] = []
    for row in rows:
        tags = _loads_tags(row.tags)
        if tag_empty:
            if tags:
                continue
        elif tag_needle and tag_needle not in tags:
            continue
        if model_empty:
            if (row.model or "").strip():
                continue
        elif model_needle and (row.model or "") != model_needle:
            continue
        if uukey_needle and (row.uukey or "") != uukey_needle:
            continue
        if field_needle and (row.field or "") != field_needle:
            continue
        if needle:
            blob = " ".join(
                [
                    row.title or "",
                    row.filename or "",
                    " ".join(tags),
                    row.model or "",
                    row.uukey or "",
                    row.field or "",
                    row.note or "",
                    row.text or "",
                ]
            ).lower()
            if needle not in blob:
                continue
        items.append(_asset_dict(row, include_text=False))
        if len(items) >= limit:
            break
    return {"items": items, "count": len(items)}


def get_asset(
    session: Session,
    ctx: Ctx,
    *,
    asset_id: str,
    include_text: bool = True,
    text_limit: int | None = None,
) -> dict[str, Any]:
    return _asset_dict(
        _get_asset(session, ctx, asset_id),
        include_text=include_text,
        text_limit=text_limit,
    )


def get_asset_bytes(session: Session, ctx: Ctx, *, asset_id: str) -> tuple[DocAsset, bytes]:
    row = _get_asset(session, ctx, asset_id)
    if not row.name:
        raise AppError("not_found", "asset has no stored blob")
    data = _store_for_row(row).get(row.name)
    return row, data


def get_asset_preview(
    session: Session,
    ctx: Ctx,
    *,
    asset_id: str,
    sheet: int = 0,
    page: int = 1,
    filters: dict[str, Any] | None = None,
    facets: bool = False,
) -> dict[str, Any]:
    row, data = get_asset_bytes(session, ctx, asset_id=asset_id)
    from builtin.doc.extract import preview_excel

    return {
        "id": row.id,
        "filename": row.filename,
        **preview_excel(
            row.filename,
            data,
            row.mime_type,
            sheet=sheet,
            page=page,
            filters=filters,
            facets=facets,
        ),
    }


def apply_extract_job(session: Session, payload: dict[str, Any]) -> None:
    asset_id = str((payload or {}).get("asset_id") or "")
    if not asset_id:
        return
    row = session.get(DocAsset, asset_id)
    if row is None:
        return
    row.text_status = "running"
    session.flush()
    try:
        if not row.name:
            raise AppError("not_found", "asset has no stored blob")
        data = _store_for_row(row).get(row.name)
        from builtin.doc.extract import extract_bytes

        result = extract_bytes(row.filename, data, row.mime_type)
        row.text = sanitize_pg_text(result.text or "")[:_MAX_TEXT_CHARS]
        row.text_method = result.method or ""
        row.text_error = sanitize_pg_text(result.error or "")[:2000]
        row.text_status = "failed" if result.error and not (result.text or "").strip() else "ready"
        row.updated_at = _now()
    except Exception as exc:  # noqa: BLE001
        row.text_status = "failed"
        row.text_error = sanitize_pg_text(str(exc))[:2000]
        row.updated_at = _now()


def _touch_origin(row: DocAsset, *, model: str | None, uukey: str | None, field: str | None) -> bool:
    changed = False
    if model is not None:
        row.model = model.strip()[:128]
        changed = True
    if uukey is not None:
        row.uukey = uukey.strip()[:64]
        changed = True
    if field is not None:
        row.field = field.strip()[:128]
        changed = True
    return changed


def sync_record_assets(
    session: Session,
    ctx: Ctx,
    *,
    model: str,
    uukey: str,
    owned: dict[str, str],
    fields: list[str],
) -> None:
    """把这条记录上仍引用的文件标上来源，并清掉这几个字段上已经拿掉的文件。

    owned 是 asset id → 字段键。fields 是这次写入里出现过的附件字段。
    没出现的字段不动，避免局部更新把别的附件清掉。
    """
    model = (model or "").strip()[:128]
    uukey = (uukey or "").strip()[:64]
    present = {str(f or "").strip() for f in fields if str(f or "").strip()}
    if not model or not uukey or not present:
        return
    wanted = {
        str(aid or "").strip(): str(field or "").strip()[:128]
        for aid, field in owned.items()
        if str(aid or "").strip() and str(field or "").strip()
    }
    rows = list(
        session.scalars(
            select(DocAsset).where(
                DocAsset.tenant == ctx.tenant,
                DocAsset.model == model,
                DocAsset.uukey == uukey,
            )
        )
    )
    seen: set[str] = set()
    for row in rows:
        if (row.field or "") not in present:
            continue
        field = wanted.get(row.id)
        if not field:
            row.model = ""
            row.uukey = ""
            row.field = ""
        elif row.field != field:
            row.field = field
        row.updated_by = ctx.user_id
        row.updated_at = _now()
        seen.add(row.id)
    for aid, field in wanted.items():
        if aid in seen:
            continue
        row = session.get(DocAsset, aid)
        if row is None or row.tenant != ctx.tenant:
            continue
        row.model = model
        row.uukey = uukey
        row.field = field
        row.updated_by = ctx.user_id
        row.updated_at = _now()
    session.flush()


def update_asset(
    session: Session,
    ctx: Ctx,
    *,
    asset_id: str,
    title: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    text: str | None = None,
    model: str | None = None,
    uukey: str | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    row = _get_asset(session, ctx, asset_id)
    origin = _touch_origin(row, model=model, uukey=uukey, field=field)
    if title is None and tags is None and note is None and text is None and not origin:
        raise AppError("validation_error", "provide title, tags, note, text, and/or origin")
    if title is not None:
        title = title.strip()
        if not title:
            raise AppError("validation_error", "title is required")
        row.title = title[:512]
    if tags is not None:
        row.tags = _dumps_tags(tags)
    if note is not None:
        row.note = sanitize_pg_text(note.strip())
    if text is not None:
        row.text = sanitize_pg_text(text)[:_MAX_TEXT_CHARS]
        row.text_status = "ready"
        row.text_method = "manual"
        row.text_error = ""
    row.updated_by = ctx.user_id
    row.updated_at = _now()
    session.flush()
    return _asset_dict(row)


def delete_asset(session: Session, ctx: Ctx, *, asset_id: str) -> dict[str, Any]:
    row = _get_asset(session, ctx, asset_id)
    payload = _asset_dict(row, include_text=False)
    name = row.name
    backend = row.type
    session.delete(row)
    session.flush()
    if name:
        try:
            settings = get_doc_settings()
            store = get_blob_store(settings)
            if backend == store.backend:
                store.delete(name)
        except AppError:
            pass
    return {"deleted": True, "asset": payload}


def model_title(model: str) -> str:
    """模型键换成配置里的名称。未知模型仍返回原键。"""
    key = (model or "").strip()
    if not key:
        return ""
    try:
        from modoor.engine.registry import get_bundle

        bundle = get_bundle(key)
    except KeyError:
        return key
    title = str(bundle.model.get("title") or "").strip()
    return title or key


def list_nav(session: Session, ctx: Ctx) -> dict[str, Any]:
    """侧栏一次返回模型和标签。没有来源、没有标签的文件分别计在 empty。"""
    rows = list(session.scalars(_scope(ctx)))
    model_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    model_empty = 0
    tag_empty = 0
    for row in rows:
        model = (row.model or "").strip()
        if not model:
            model_empty += 1
        else:
            model_counts[model] = model_counts.get(model, 0) + 1
        loaded = _loads_tags(row.tags)
        if not loaded:
            tag_empty += 1
        for tag in loaded:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    models = [
        {"model": k, "title": model_title(k), "count": v}
        for k, v in sorted(model_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    tags = [
        {"tag": k, "count": v}
        for k, v in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    return {
        "models": models,
        "model_empty": model_empty,
        "tags": tags,
        "tag_empty": tag_empty,
    }
