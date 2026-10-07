"""base_tbl column settings: global row per model view."""

from __future__ import annotations

import pytest

from builtin.base.tbl import (
    TBL_LEVEL_GLOBAL,
    get_table_setting,
    normalize_tbl_data,
    upsert_table_setting,
)
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx
from modoor.testing import configure_test_db


@pytest.fixture()
def _env(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="t1",
        MODOOR_CONFIRM_SECRET="secret",
    )
    bootstrap(get_settings())
    yield
    get_settings.cache_clear()


def test_normalize_tbl_data_empty_is_none():
    assert normalize_tbl_data(None) is None
    assert normalize_tbl_data({"order": [], "hidden": []}) is None
    assert normalize_tbl_data({"order": ["basic.name", " basic.name "], "hidden": ["basic.phone"]}) == {
        "order": ["basic.name"],
        "hidden": ["basic.phone"],
    }


def test_upsert_get_and_delete(_env):
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        assert get_table_setting(session, ctx, model="capacity.company", using="default") is None
        saved = upsert_table_setting(
            session,
            ctx,
            model="capacity.company",
            using="default",
            data={"order": ["basic.name", "basic.uukey"], "hidden": ["basic.uukey"]},
        )
        assert saved is not None
        assert saved["level"] == TBL_LEVEL_GLOBAL
        assert saved["using"] == "default"
        got = get_table_setting(session, ctx, model="capacity.company", using="default")
        assert got is not None
        assert got["data"]["hidden"] == ["basic.uukey"]
        assert upsert_table_setting(session, ctx, model="capacity.company", using="default", data=None) is None
        assert get_table_setting(session, ctx, model="capacity.company", using="default") is None


def test_model_required(_env):
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        with pytest.raises(AppError):
            upsert_table_setting(session, ctx, model="  ", data={"order": ["basic.name"]})
