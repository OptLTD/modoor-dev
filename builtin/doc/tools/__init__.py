"""Doc MCP tools — query / read / upload."""

from __future__ import annotations

import base64
from typing import Any

from modoor.core.errors import AppError
from modoor.runtime.tool import run_tool
from builtin.doc import domain as doc_domain


def query(
    q: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> str:
    """Search document assets (read-only). Use doc.read for one asset.

    q matches title, filename, tags, origin, note, and extracted text.
    tag keeps assets that include that exact tag.
    """
    args: dict[str, Any] = {"q": q, "tag": tag, "limit": limit}

    def _inner(session, ctx, _settings):
        return doc_domain.list_assets(
            session, ctx, q=q or None, tag=tag or None, limit=limit
        )

    return run_tool("doc.query", args, _inner, readonly=True)


def read(asset_id: str, full_text: bool = True) -> str:
    """Read one document asset by id.

    Includes tags and origin (model, uukey, field). field is the schema key.
    full_text=True (default): include full extracted text for AI reading.
    full_text=False: metadata + truncated text preview.
    """
    args = {"asset_id": asset_id, "full_text": full_text}

    def _inner(session, ctx, _settings):
        if not (asset_id or "").strip():
            raise AppError("validation_error", "asset_id required")
        if full_text:
            asset = doc_domain.get_asset(
                session, ctx, asset_id=asset_id, include_text=True
            )
            return {
                "id": asset["id"],
                "title": asset["title"],
                "filename": asset["filename"],
                "tags": asset["tags"],
                "model": asset.get("model") or "",
                "uukey": asset.get("uukey") or "",
                "field": asset.get("field") or "",
                "text_status": asset.get("text_status") or "ready",
                "text_method": asset.get("text_method") or "",
                "text": asset.get("text") or "",
            }
        return {
            "item": doc_domain.get_asset(
                session, ctx, asset_id=asset_id, text_limit=8_000
            )
        }

    return run_tool("doc.read", args, _inner, readonly=True)


def upload(
    title: str | None = None,
    text: str | None = None,
    filename: str | None = None,
    content_base64: str | None = None,
    mime_type: str | None = None,
    tags: list[str] | None = None,
    note: str = "",
    model: str = "",
    uukey: str = "",
    field: str = "",
) -> str:
    """Upload a document asset (blocked when Agent is read-only).

    Text: title + text. Binary: filename + content_base64.
    tags are human labels. model, uukey, and field record the owning record
    field; field stores the schema key, for example files.id_card.
    """
    args: dict[str, Any] = {
        "title": title,
        "text": text,
        "filename": filename,
        "content_base64": "(set)" if content_base64 else None,
        "mime_type": mime_type,
        "tags": tags,
        "note": note,
        "model": model,
        "uukey": uukey,
        "field": field,
    }

    def _inner(session, ctx, _settings):
        tag_list = [str(t).strip() for t in (tags or []) if str(t).strip()]
        b64 = (content_base64 or "").strip()
        if b64:
            try:
                raw = base64.b64decode(b64, validate=False)
            except Exception as exc:  # noqa: BLE001
                raise AppError("validation_error", "content_base64 is invalid") from exc
            fname = (filename or "").strip() or "file.bin"
            asset = doc_domain.create_asset(
                session,
                ctx,
                filename=fname,
                data=raw,
                title=title,
                mime_type=mime_type,
                tags=tag_list or None,
                note=note or "",
                model=model,
                uukey=uukey,
                field=field,
            )
            return {"action": "upload", "asset": asset}

        if text is None and not (title or "").strip():
            raise AppError(
                "validation_error",
                "provide title+text, or filename+content_base64",
            )
        asset = doc_domain.create_text_asset(
            session,
            ctx,
            title=(title or "").strip() or "Untitled",
            text=text if text is not None else "",
            tags=tag_list or None,
            note=note or "",
            filename=filename,
            model=model,
            uukey=uukey,
            field=field,
        )
        return {"action": "upload", "asset": asset}

    return run_tool("doc.upload", args, _inner)


def register(mcp) -> None:
    mcp.tool(name="doc.query")(query)
    mcp.tool(name="doc.read")(read)
    mcp.tool(name="doc.upload")(upload)
