"""一份文件只属于一条记录：来源写在 asset 的 model、uukey、field 上。"""

from __future__ import annotations

import json

import pytest

from builtin.doc import domain as doc_domain
from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx
from modoor.testing import configure_test_db


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_DOC_STORAGE="local",
        MODOOR_DOC_LOCAL_ROOT=str(tmp_path),
        MODOOR_DOC_OCR="0",
        MODOOR_JOBS_INPROCESS="0",
    )
    bootstrap(get_settings())
    yield
    get_settings.cache_clear()


def test_sync_record_assets_sets_and_clears_origin():
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        kept = doc_domain.create_asset(
            session, ctx, filename="id.png", data=b"id-card", title="身份证"
        )
        dropped = doc_domain.create_asset(
            session, ctx, filename="old.png", data=b"old", title="旧证"
        )
        doc_domain.sync_record_assets(
            session,
            ctx,
            model="fleet.vehicle",
            uukey="VEH12345",
            owned={kept["id"]: "files.id_card", dropped["id"]: "files.id_card"},
            fields=["files.id_card"],
        )
        kept_row = doc_domain.get_asset(session, ctx, asset_id=kept["id"], include_text=False)
        assert kept_row["model"] == "fleet.vehicle"
        assert kept_row["uukey"] == "VEH12345"
        assert kept_row["field"] == "files.id_card"

        doc_domain.sync_record_assets(
            session,
            ctx,
            model="fleet.vehicle",
            uukey="VEH12345",
            owned={kept["id"]: "files.id_card"},
            fields=["files.id_card"],
        )
        dropped_row = doc_domain.get_asset(
            session, ctx, asset_id=dropped["id"], include_text=False
        )
        assert dropped_row["model"] == ""
        assert dropped_row["uukey"] == ""
        assert dropped_row["field"] == ""
        still = doc_domain.get_asset(session, ctx, asset_id=kept["id"], include_text=False)
        assert still["uukey"] == "VEH12345"

        listed = doc_domain.list_assets(
            session, ctx, model="fleet.vehicle", uukey="VEH12345", field="files.id_card"
        )
        assert [item["id"] for item in listed["items"]] == [kept["id"]]
        nav = doc_domain.list_nav(session, ctx)
        assert nav["models"] == [{"model": "fleet.vehicle", "title": "车辆管理", "count": 1}]
        assert nav["model_empty"] == 1
        empty_models = doc_domain.list_assets(session, ctx, model_empty=True)
        assert [item["id"] for item in empty_models["items"]] == [dropped["id"]]
        assert nav["tag_empty"] == 2
        empty_tags = doc_domain.list_assets(session, ctx, tag_empty=True)
        assert {item["id"] for item in empty_tags["items"]} == {kept["id"], dropped["id"]}


def test_mcp_tools_tag_filter_and_origin():
    from builtin.doc.tools import query, read, upload

    uploaded = json.loads(
        upload(
            title="许可证",
            text="道路运输许可",
            tags=["道路许可证"],
            model="fleet.vehicle",
            uukey="VEH12345",
            field="files.license",
        )
    )
    asset = uploaded["result"]["asset"]
    assert asset["model"] == "fleet.vehicle"
    assert asset["uukey"] == "VEH12345"
    assert asset["field"] == "files.license"
    assert asset["tags"] == ["道路许可证"]

    found = json.loads(query(tag="道路许可证"))
    assert asset["id"] in {item["id"] for item in found["result"]["items"]}
    missed = json.loads(query(tag="现场调研"))
    assert asset["id"] not in {item["id"] for item in missed["result"]["items"]}

    detail = json.loads(read(asset_id=asset["id"]))
    body = detail["result"]
    assert body["model"] == "fleet.vehicle"
    assert body["uukey"] == "VEH12345"
    assert body["field"] == "files.license"
    assert body["tags"] == ["道路许可证"]
    assert "道路运输许可" in body["text"]
