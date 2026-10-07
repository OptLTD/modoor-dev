from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx
from modoor.web.app import app
from modoor.web.nav import clear_ui_cache
from builtin.base import domain as base_domain
from modoor.testing import configure_test_db


@pytest.fixture()
def client(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
    )
    get_settings.cache_clear()
    clear_ui_cache()
    clear_bundle_cache()
    reload_engine_caches()
    bootstrap()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_shell_modules_filtered_by_role_nodes(client: TestClient):
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        limited = base_domain.create_user(
            session, ctx, username="limited", realname="Limited", password="pw"
        )
        role = base_domain.create_role(session, ctx, name="Wiki Doc Only")
        base_domain.set_role_nodes(
            session,
            ctx,
            role_id=role["id"],
            nodes=["wiki.page.read", "doc.asset.read"],
        )
        base_domain.assign_role(
            session, ctx, user_id=limited["id"], role_id=role["id"]
        )
        user_id = limited["id"]

    logged = client.post(
        "/api/auth/login", json={"username": "limited", "password": "pw"}
    )
    assert logged.status_code == 200
    assert logged.json()["home"] == "/"
    assert logged.json()["module"] is None

    shell = client.get("/api/shell/modules")
    assert shell.status_code == 200
    ids = {m["id"] for m in shell.json()["modules"]}
    assert ids == {"wiki", "doc"}

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    body = home.text
    assert "工作台" in body
    assert "wiki" in body and "doc" in body
    assert 'href="' in body

    blocked = client.get("/go/sale")
    assert blocked.status_code == 403

    ok = client.get("/go/wiki", follow_redirects=False)
    assert ok.status_code in (302, 303)

    with session_scope() as session:
        access = base_domain.list_user_abilities(session, ctx, user_id=user_id)
        assert access["unrestricted"] is False
        assert "wiki.page.read" in access["abilities"]


def test_admin_role_sees_all_enabled_modules(client: TestClient):
    logged = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert logged.status_code == 200
    shell = client.get("/api/shell/modules")
    assert shell.status_code == 200
    ids = {m["id"] for m in shell.json()["modules"]}
    assert "base" in ids and "sale" in ids and "wiki" in ids
