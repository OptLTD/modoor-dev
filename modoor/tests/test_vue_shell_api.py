from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.web.app import app
from modoor.web.nav import clear_ui_cache
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
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


def test_vue_shell_apis(client: TestClient):
    logged = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    assert str(logged.json()["user"]["uukey"]).startswith("USER")

    me = client.get("/api/auth/profile")
    assert me.status_code == 200
    assert str(me.json()["user"]["uukey"]).startswith("USER")
    assert isinstance(me.json()["user"].get("tenants"), list)
    assert me.json()["user"]["tenants"]

    users = client.get("/api/base/users")
    assert users.status_code == 200
    assert users.json()["items"]

    user_form = client.post(
        "/api/record/input",
        json={"model": "base.user", "using": "default", "scene": "INSERT"},
    )
    assert user_form.status_code == 200, user_form.text
    field_keys = {f["uukey"] for f in user_form.json()["input"]["fields"]}
    assert "basic.code" in field_keys
    assert "basic.team_id" in field_keys
    assert "basic.name" in field_keys
    assert "basic.utime" in field_keys
    assert "basic.phone" in field_keys
    assert "basic.email" in field_keys
    assert "basic.remark" in field_keys
    assert "basic.username" not in field_keys
    assert "basic.realname" not in field_keys
    assert "basic.password" not in field_keys
    assert "basic.active" not in field_keys
    team_field = next(f for f in user_form.json()["input"]["fields"] if f["uukey"] == "basic.team_id")
    assert team_field["ftype"].upper() == "OPTIONAL"
    assert str(team_field.get("extra", {}).get("editable") or "").upper() == "INSERT"
    team_opts = user_form.json()["input"]["refers"]["basic.team_id"]
    assert team_opts
    assert all("uukey" in o and "label" in o for o in team_opts)

    listed = client.post(
        "/api/record/search",
        json={"model": "base.user", "using": "default", "scene": "SEARCH", "page": 1, "size": 50},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["refers"]["basic.team_id"]
    user_row = listed.json()["values"][0]
    assert str(user_row["basic.code"]).startswith("USER")
    assert user_row["basic.state"] in ("1", 1)
    assert user_row.get("basic.utime")

    roles = client.get("/api/base/roles")
    assert roles.status_code == 200
    assert "roles" in roles.json()

    mods = client.get("/api/base/modules")
    assert mods.status_code == 200
    assert any(m["id"] == "base" for m in mods.json()["modules"])

    schema = client.post("/api/record/schema", json={"model": "base.user", "using": "default"})
    assert schema.status_code == 200, schema.text
    click_ids = {c["uukey"] for c in schema.json()["table"]["clicks"]}
    assert "create" in click_ids
    assert "delete" not in click_ids
    assert {"set_role", "set_pswd", "enable", "disable"} <= click_ids
    grouped = {c["uukey"]: c.get("group") for c in schema.json()["table"]["clicks"]}
    assert grouped["set_role"] == grouped["set_pswd"] == grouped["enable"] == grouped["disable"] == "account"
    assert not grouped.get("create")

    admin = users.json()["items"][0]
    user_roles = client.get(f"/api/base/users/{admin['uukey']}/roles")
    assert user_roles.status_code == 200, user_roles.text
    assert user_roles.json()["user_id"] == admin["id"]
    assert "roles" in user_roles.json()
    assert "assigned" in user_roles.json()

    wiki = client.get("/api/wiki/pages")
    assert wiki.status_code == 200

    shell = client.get("/api/shell/modules")
    assert shell.status_code == 200
    ids = {m["id"] for m in shell.json()["modules"]}
    assert "base" in ids and "sale" in ids


def test_registry_catalog_with_ticket_without_session(client: TestClient):
    logged = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    user = logged.json()["user"]
    from modoor.platform.tickets import issue_ticket

    ticket = issue_ticket(user_id=int(user["id"]), tenant=int(user["tenant"]))
    client.cookies.clear()
    catalog = client.get("/api/apps/catalog", headers={"X-Modoor-Ticket": ticket})
    assert catalog.status_code == 200, catalog.text
    profile = catalog.json().get("profile") or {}
    assert profile.get("username")
    assert profile.get("tenant") == user["tenant"]
