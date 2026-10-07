from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
from modoor.web.app import app
from addon.sale import domain as sale_domain
from modoor.core.ctx import Ctx
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
    clear_bundle_cache()
    reload_engine_caches()
    from modoor.platform.bootstrap import bootstrap

    bootstrap()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    clear_bundle_cache()
    reload_engine_caches()


def _login(client: TestClient) -> None:
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, res.text


def test_schema_search_input_upsert_flow(client: TestClient):
    _login(client)

    schema = client.post(
        "/api/record/schema",
        json={"model": "sale.order", "using": "table", "scene": "SEARCH"},
    )
    assert schema.status_code == 200, schema.text
    body = schema.json()
    assert body["model"] == "sale.order"
    assert body["table"]["fields"]
    assert any(f["uukey"] == "basic.partner" for f in body["table"]["fields"])

    # seed via domain
    with session_scope() as session:
        sale_domain.create_order(
            session,
            Ctx(tenant=1, user_id=1, team_id=1),
            partner="Alice",
            lines=[{"product_name": "Widget", "qty": 2, "unit_price": 10}],
            note="n1",
        )

    search = client.post(
        "/api/record/search",
        json={
            "model": "sale.order",
            "using": "default",
            "scene": "SEARCH",
            "page": 1,
            "size": 50,
            "query": {"basic.partner": "Alice"},
        },
    )
    assert search.status_code == 200, search.text
    data = search.json()
    assert data["count"] >= 1
    assert data["values"]
    row = data["values"][0]
    assert "basic.uukey" in row
    assert row["basic.partner"] == "Alice"
    assert row["amount.total"] == 20.0
    uukey = row["basic.uukey"]

    detail = client.post(
        "/api/record/input",
        json={"model": "sale.order", "using": "default", "scene": "DETAIL", "uukey": uukey},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["input"]["values"]["basic.partner"] == "Alice"

    upsert = client.post(
        "/api/record/upsert",
        json={
            "model": "sale.order",
            "using": "default",
            "scene": "UPDATE",
            "batch": [
                {
                    "uukey": uukey,
                    "basic.uukey": uukey,
                    "basic.partner": "Alice Co",
                    "partner": "Alice Co",
                    "basic.status": "draft",
                    "status": "draft",
                    "basic.note": "updated",
                }
            ],
        },
    )
    assert upsert.status_code == 200, upsert.text
    recs = upsert.json()["records"]
    assert recs[0]["current"]["basic.partner"] == "Alice Co"
