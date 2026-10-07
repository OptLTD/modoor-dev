from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.platform.services import clear_live_services
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
    clear_live_services()
    bootstrap()
    with TestClient(app) as c:
        yield c
    clear_live_services()
    get_settings.cache_clear()


def _login(client: TestClient) -> None:
    logged = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200, logged.text


def _register_iot(client: TestClient):
    res = client.post(
        "/api/apps",
        headers={"X-API-Key": "test-key"},
        json={
            "id": "iot",
            "app_name": "车联网",
            "entry_url": "http://127.0.0.1:8089/monitor",
            "manifest": {
                "id": "iot",
                "summary": "JT808 monitor",
                "ui-web": {"kind": "external", "label": "IoT"},
            },
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_registered_service_offline_and_disable(client: TestClient):
    _login(client)
    _register_iot(client)

    mods = client.get("/api/base/modules")
    assert mods.status_code == 200, mods.text
    iot = next(m for m in mods.json()["modules"] if m["id"] == "iot")
    assert iot["enabled"] is True
    assert iot["kind"] == "external"
    assert iot["online"] is True

    shell = client.get("/api/shell/modules")
    assert "iot" in {m["id"] for m in shell.json()["modules"]}
    hit = next(m for m in shell.json()["modules"] if m["id"] == "iot")
    assert hit["online"] is True

    catalog = client.get("/api/apps/catalog")
    assert catalog.status_code == 200
    assert "iot" in {m["id"] for m in catalog.json()["modules"]}

    clear_live_services()

    mods = client.get("/api/base/modules")
    iot = next(m for m in mods.json()["modules"] if m["id"] == "iot")
    assert iot["enabled"] is True
    assert iot["online"] is False

    shell = client.get("/api/shell/modules")
    hit = next(m for m in shell.json()["modules"] if m["id"] == "iot")
    assert hit["online"] is False
    assert hit["href"].endswith("/go/iot")

    beat = client.post(
        "/api/apps/iot/heartbeat",
        headers={"X-API-Key": "test-key"},
        json={"entry_url": "http://127.0.0.1:8089/monitor"},
    )
    assert beat.status_code == 200, beat.text
    mods = client.get("/api/base/modules")
    iot = next(m for m in mods.json()["modules"] if m["id"] == "iot")
    assert iot["online"] is True

    toggled = client.post("/api/base/modules/iot/toggle", json={"enabled": False})
    assert toggled.status_code == 200, toggled.text

    mods = client.get("/api/base/modules")
    iot = next(m for m in mods.json()["modules"] if m["id"] == "iot")
    assert iot["enabled"] is False

    shell = client.get("/api/shell/modules")
    assert "iot" not in {m["id"] for m in shell.json()["modules"]}

    gone = client.get("/go/iot", follow_redirects=False)
    assert gone.status_code == 404

    client.post("/api/base/modules/iot/toggle", json={"enabled": True})
    shell = client.get("/api/shell/modules")
    assert "iot" in {m["id"] for m in shell.json()["modules"]}
