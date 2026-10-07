"""builtin.doc JSON API — assets, nav, content stream."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.web.api_util import ctx_of, http_error, require_user
from builtin.doc import domain as doc_domain

router = APIRouter(prefix="/api/doc", tags=["doc"])


class TextCreate(BaseModel):
    title: str
    text: str = ""
    tags: list[str] = Field(default_factory=list)
    note: str = ""
    filename: str | None = None


class AssetUpdate(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    note: str | None = None
    text: str | None = None
    model: str | None = None
    uukey: str | None = None
    field: str | None = None


def _parse_tags(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    text = str(raw).strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]


def _content_disposition(disposition: str, filename: str) -> str:
    """RFC 5987 header — ASCII fallback + UTF-8 filename* (Starlette is latin-1)."""
    name = (filename or "file").replace('"', "").replace("\r", "").replace("\n", "")
    ascii_name = name.encode("ascii", "ignore").decode("ascii").strip() or "file"
    if ascii_name.startswith("."):
        ascii_name = f"file{ascii_name}"
    return (
        f"{disposition}; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(name)}"
    )


@router.get("/assets")
def api_list_assets(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
    model: str | None = None,
    tag_empty: int = 0,
    model_empty: int = 0,
    uukey: str | None = None,
    field: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return doc_domain.list_assets(
                session,
                ctx_of(user),
                q=q,
                tag=tag,
                model=model,
                tag_empty=bool(tag_empty),
                model_empty=bool(model_empty),
                uukey=uukey,
                field=field,
                limit=limit,
            )
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/assets/{asset_id}")
def api_get_asset(request: Request, asset_id: str, full: int = 0) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return {
                "asset": doc_domain.get_asset(
                    session,
                    ctx_of(user),
                    asset_id=asset_id,
                    text_limit=None if full else 20_000,
                )
            }
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/assets/{asset_id}/content")
def api_get_content(request: Request, asset_id: str, download: int = 0) -> Response:
    user = require_user(request)
    try:
        with session_scope() as session:
            row, data = doc_domain.get_asset_bytes(
                session, ctx_of(user), asset_id=asset_id
            )
            filename = row.filename
            mime_type = row.mime_type or "application/octet-stream"
        disposition = "attachment" if download else "inline"
        headers = {
            "Content-Disposition": _content_disposition(disposition, filename),
            "Cache-Control": "private, max-age=60",
        }
        return Response(content=data, media_type=mime_type, headers=headers)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/assets/{asset_id}/preview")
def api_get_preview(
    request: Request,
    asset_id: str,
    sheet: int = 0,
    page: int = 1,
    filters: str | None = None,
    facets: bool = False,
) -> dict[str, Any]:
    user = require_user(request)
    parsed: dict[str, Any] | None = None
    if filters:
        try:
            raw = json.loads(filters)
        except json.JSONDecodeError as exc:
            raise http_error(AppError("invalid_filters", "invalid filters")) from exc
        if not isinstance(raw, dict):
            raise http_error(AppError("invalid_filters", "invalid filters"))
        parsed = raw
    try:
        with session_scope() as session:
            return doc_domain.get_asset_preview(
                session,
                ctx_of(user),
                asset_id=asset_id,
                sheet=sheet,
                page=page,
                filters=parsed,
                facets=facets,
            )
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/assets")
async def api_upload_asset(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    note: str = Form(default=""),
    model: str = Form(default=""),
    uukey: str = Form(default=""),
    field: str = Form(default=""),
) -> dict[str, Any]:
    user = require_user(request)
    try:
        raw = await file.read()
        with session_scope() as session:
            asset = doc_domain.create_asset(
                session,
                ctx_of(user),
                filename=file.filename or "file",
                data=raw,
                title=title,
                mime_type=file.content_type,
                tags=_parse_tags(tags),
                note=note,
                model=model,
                uukey=uukey,
                field=field,
            )
        return {"ok": True, "asset": asset}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/assets/text")
def api_create_text(request: Request, body: TextCreate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            asset = doc_domain.create_text_asset(
                session,
                ctx_of(user),
                title=body.title,
                text=body.text,
                tags=body.tags,
                note=body.note,
                filename=body.filename,
            )
        return {"ok": True, "asset": asset}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.patch("/assets/{asset_id}")
def api_update_asset(request: Request, asset_id: str, body: AssetUpdate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            asset = doc_domain.update_asset(
                session,
                ctx_of(user),
                asset_id=asset_id,
                title=body.title,
                tags=body.tags,
                note=body.note,
                text=body.text,
                model=body.model,
                uukey=body.uukey,
                field=body.field,
            )
        return {"ok": True, "asset": asset}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/assets/{asset_id}")
def api_delete_asset(request: Request, asset_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return doc_domain.delete_asset(session, ctx_of(user), asset_id=asset_id)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/nav")
def api_list_nav(request: Request) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return doc_domain.list_nav(session, ctx_of(user))
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


def register(app, _kit) -> None:
    app.include_router(router)
