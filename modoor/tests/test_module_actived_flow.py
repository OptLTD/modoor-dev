"""Lazy module actived + schema smoke tests (platform / builtin only)."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.platform.loader import ensure_module_schema, modules_to_load
from modoor.platform.module_state import (
    discover_manifests,
    set_module_enabled,
    yaml_actived_module_ids,
)
from modoor.testing import configure_test_db


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("MODOOR_USER_ID", raising=False)
    monkeypatch.delenv("MODOOR_TEAM_ID", raising=False)


def test_yaml_actived_defaults(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
        MODOOR_LOAD_ALL_MODULES="0",
    )
    manifests = {m["id"]: m for m in discover_manifests()}
    assert manifests["base"]["actived"] is True
    actived = yaml_actived_module_ids()
    assert "base" in actived
    loaded = modules_to_load(get_settings())
    assert "base" in loaded


def test_lazy_schema_on_enable(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
        MODOOR_LOAD_ALL_MODULES="0",
    )
    result = bootstrap(get_settings())
    with session_scope() as session:
        insp = inspect(session.get_bind())
        # wiki actived:false → table may be absent when not load-all
        assert "base_user" in insp.get_table_names() or "base_user" in {
            t for t in insp.get_table_names()
        }

    # skill was false; enabling installs schema
    ensure_module_schema("skill")
    with session_scope() as session:
        insp = inspect(session.get_bind())
        names = set(insp.get_table_names())
        assert "skill_item" in names
        set_module_enabled(session, result["tenant_id"], "skill", True)
