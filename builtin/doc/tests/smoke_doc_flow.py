"""Smoke: doc asset upload / search / text / delete + storage backend guard."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from modoor.core.db import init_db, session_scope  # noqa: E402
from modoor.core.errors import AppError  # noqa: E402
from modoor.core.settings import get_settings  # noqa: E402
from modoor.platform.bootstrap import bootstrap  # noqa: E402
from modoor.runtime.auth import resolve_ctx  # noqa: E402
from modoor.runtime.jobs import run_pending  # noqa: E402
from builtin.doc import domain as doc_domain  # noqa: E402
from builtin.doc.settings import DocSettings, get_doc_settings  # noqa: E402
from builtin.doc.storage import get_blob_store  # noqa: E402
from modoor.testing import ensure_database, test_database_url  # noqa: E402


def main() -> None:
    doc_root = tempfile.mkdtemp(prefix="modoor-doc-")
    os.environ["DATABASE_URL"] = test_database_url()
    os.environ["MODOOR_DOC_STORAGE"] = "local"
    os.environ["MODOOR_DOC_LOCAL_ROOT"] = doc_root
    os.environ["MODOOR_JOBS_INPROCESS"] = "0"
    os.environ["MODOOR_DOC_OCR"] = "0"
    os.environ.setdefault("MODOOR_API_KEY", "dev-key-change-me")
    os.environ.setdefault("MODOOR_TENANT", "demo")
    os.environ.setdefault("MODOOR_CONFIRM_SECRET", "dev-confirm-secret-change-me")
    get_settings.cache_clear()
    get_doc_settings.cache_clear()
    ensure_database(os.environ["DATABASE_URL"])

    settings = get_settings()
    init_db(settings, recreate=True)
    bootstrap()
    ctx = resolve_ctx(settings)

    # s3 not implemented
    os.environ["MODOOR_DOC_STORAGE"] = "s3"
    get_doc_settings.cache_clear()
    try:
        get_blob_store(DocSettings())
        raise SystemExit("expected not_implemented for s3")
    except AppError as exc:
        assert exc.code == "not_implemented", exc
    os.environ["MODOOR_DOC_STORAGE"] = "local"
    get_doc_settings.cache_clear()

    with session_scope() as session:
        txt = doc_domain.create_asset(
            session,
            ctx,
            filename="readme.txt",
            data=b"hello doc warehouse\ntag-me",
            title="Readme",
            tags=["smoke", "txt"],
        )
        assert txt["id"]
        assert txt.get("text_status") == "pending"

        png = doc_domain.create_asset(
            session,
            ctx,
            filename="dot.png",
            data=(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
                b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            ),
            title="Dot",
            tags=["smoke", "img"],
            mime_type="image/png",
        )

        pdf = doc_domain.create_asset(
            session,
            ctx,
            filename="blank.pdf",
            data=b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
            title="Blank PDF",
            tags=["smoke", "pdf"],
            mime_type="application/pdf",
        )

        # tiny docx (zip with word/document.xml)
        import zipfile
        from io import BytesIO

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>docx hello</w:t></w:r></w:p></w:body></w:document>",
            )
        docx = doc_domain.create_asset(
            session,
            ctx,
            filename="note.docx",
            data=buf.getvalue(),
            title="Note",
            tags=["smoke", "docx"],
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    run_pending(limit=20)

    with session_scope() as session:
        txt = doc_domain.get_asset(session, ctx, asset_id=txt["id"])
        assert txt.get("text_status") == "ready"
        assert "hello" in (txt.get("text") or "")

        docx = doc_domain.get_asset(session, ctx, asset_id=docx["id"])
        assert "docx hello" in (docx.get("text") or "")

        found = doc_domain.list_assets(session, ctx, q="warehouse", tag="txt")
        assert found["count"] >= 1
        assert any(i["id"] == txt["id"] for i in found["items"])

        by_tag = doc_domain.list_assets(session, ctx, tag="img")
        assert any(i["id"] == png["id"] for i in by_tag["items"])

        text = doc_domain.get_asset(session, ctx, asset_id=txt["id"])
        assert "warehouse" in (text.get("text") or "")

        row, data = doc_domain.get_asset_bytes(session, ctx, asset_id=pdf["id"])
        assert row.filename == "blank.pdf"
        assert data.startswith(b"%PDF")

        nav = doc_domain.list_nav(session, ctx)
        assert any(t["tag"] == "smoke" for t in nav["tags"])

        deleted = doc_domain.delete_asset(session, ctx, asset_id=txt["id"])
        assert deleted["deleted"] is True

        store = get_blob_store()
        assert not store.exists(txt["name"])

        for aid in (png["id"], pdf["id"], docx["id"]):
            doc_domain.delete_asset(session, ctx, asset_id=aid)

    print("doc smoke ok")


if __name__ == "__main__":
    main()
