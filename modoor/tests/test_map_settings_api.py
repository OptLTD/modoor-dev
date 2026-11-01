"""Global-settings API for map provider/tokens."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from inbuilt.base import domain as base_domain
from inbuilt.base.setting import MAP_TYPE, get_map_settings
from modoor.core import maps
from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx
from modoor.testing import configure_test_db
from modoor.web.app import app
from modoor.web.nav import clear_ui_cache


@pytest.fixture()
def client(monkeypatch):
    # Empty values override `.env`, so the DB round-trip starts unconfigured.
    for key in ("MODOOR_MAP_PROVIDER", "MODOOR_MAP_TOKEN1", "MODOOR_MAP_TOKEN2"):
        monkeypatch.setenv(key, "")
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
    # The test database is reused; start from a clean map-settings row.
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        row = base_domain.get_config(session, ctx, mod="base", type=MAP_TYPE)
        if row is not None:
            session.delete(row)
    with TestClient(app) as c:
        logged = c.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert logged.status_code == 200, logged.text
        c.headers.update({"X-Modoor-Role": "SUPERUSER"})
        yield c
    get_settings.cache_clear()


def test_map_settings_roundtrip_never_returns_tokens(
    client: TestClient, monkeypatch
):
    empty = client.get("/api/map/config")
    assert empty.status_code == 200
    assert empty.json()["configured"] is False

    settings = client.get("/api/map/settings")
    assert settings.status_code == 200
    body = settings.json()
    assert body["canEdit"] is True
    assert body["token1Set"] is False
    assert body["settings"]["token1"] == ""

    bad = client.put("/api/map/settings", json={"provider": "nope"})
    assert bad.status_code == 400

    saved = client.put(
        "/api/map/settings",
        json={"provider": "tianditu", "token1": "browser-key", "token2": "server-key"},
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["configured"] is True
    assert payload["token1Set"] is True
    assert payload["token2Set"] is True
    assert "browser-key" not in json.dumps(payload)
    assert "server-key" not in json.dumps(payload)

    config = client.get("/api/map/config")
    assert config.status_code == 200
    assert config.json()["configured"] is True
    assert "browser-key" not in config.text

    # Same provider + omitted tokens keeps the stored values.
    same = client.put("/api/map/settings", json={"provider": "tianditu"})
    assert same.status_code == 200, same.text
    assert same.json()["token1Set"] is True
    assert same.json()["token2Set"] is True

    # Switching provider drops tokens instead of reusing another provider's key.
    changed = client.put("/api/map/settings", json={"provider": "amap"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["provider"] == "amap"
    assert changed.json()["token1Set"] is False
    assert changed.json()["configured"] is False
    assert changed.json()["settings"]["token1"] == ""

    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        stored = get_map_settings(session, ctx)
    assert stored == {"provider": "amap", "token1": "", "token2": ""}

    # Static map proxy: browser key is rejected, server key returns the image.
    class _Img:
        def __init__(self, content=b"\x89PNG\r\n\x1a\n", content_type="image/png"):
            self.content = content
            self.headers = {"content-type": content_type}

        def raise_for_status(self) -> None:
            return None

    def get(url, params=None, **kwargs):
        _ = (url, kwargs)
        if str((params or {}).get("tk") or "") == "browser-key":
            raise maps.httpx.HTTPStatusError(
                "forbidden",
                request=maps.httpx.Request("GET", "https://example.test"),
                response=maps.httpx.Response(403),
            )
        return _Img()

    saved = client.put(
        "/api/map/settings",
        json={"provider": "tianditu", "token1": "browser-key", "token2": "server-key"},
    )
    assert saved.status_code == 200, saved.text
    monkeypatch.setattr(maps.httpx, "get", get)

    res = client.get(
        "/api/map/static",
        params={"lat": 31.99981, "lng": 120.24875, "zoom": 16},
    )

    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("image/")
    assert res.content.startswith(b"\x89PNG")

    missing = client.get("/api/map/static")
    assert missing.status_code == 400
