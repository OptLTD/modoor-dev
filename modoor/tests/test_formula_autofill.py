"""Unit + API tests for formula autofill engine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modoor.core.settings import get_settings
from modoor.engine.formula import (
    apply_formulas,
    ensure_fields_depends,
    eval_formula,
    parse_depends_from_formula,
)
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
from modoor.web.app import app
from modoor.testing import configure_test_db


def test_parse_depends_from_formula():
    assert parse_depends_from_formula("basic.price*basic.quantity") == [
        "basic.price",
        "basic.quantity",
    ]
    assert "runtime.departTime" in parse_depends_from_formula(
        "HOURS(runtime.departTime-runtime.loadingTime)"
    )


def test_apply_simple_product():
    fields = [
        {"uukey": "basic.quantity", "group": "basic", "field": "quantity", "ftype": "NUMERIC", "extra": {}},
        {"uukey": "basic.price", "group": "basic", "field": "price", "ftype": "NUMERIC", "extra": {}},
        {
            "uukey": "basic.total",
            "group": "basic",
            "field": "total",
            "ftype": "NUMERIC",
            "extra": {
                "formula": "basic.price*basic.quantity",
                "depends": ["basic.quantity", "basic.price"],
                "precision": 3,
            },
        },
    ]
    out = apply_formulas(fields, {"basic.quantity": 2, "basic.price": 3.5})
    assert float(out["basic.total"]) == 7.0


def test_apply_infers_depends_and_defaults():
    fields = [
        {"uukey": "basic.quantity", "group": "basic", "field": "quantity", "ftype": "NUMERIC", "extra": {}},
        {"uukey": "basic.price", "group": "basic", "field": "price", "ftype": "NUMERIC", "extra": {}},
        {
            "uukey": "basic.total",
            "group": "basic",
            "field": "total",
            "ftype": "NUMERIC",
            "extra": {"formula": "basic.price*basic.quantity", "precision": 2},
        },
    ]
    ensured = ensure_fields_depends(fields)
    total = next(f for f in ensured if f["uukey"] == "basic.total")
    assert set(total["extra"]["depends"]) == {"basic.price", "basic.quantity"}
    out = apply_formulas(ensured, {"basic.price": 4})
    # missing quantity → 0
    assert float(out["basic.total"]) == 0.0


def test_hours_datetime_diff():
    code = "HOURS(runtime.departTime-runtime.loadingTime)"
    env = {
        "runtime": {
            "loadingTime": "2024-01-01 08:00:00",
            "departTime": "2024-01-01 10:30:00",
        }
    }
    assert abs(float(eval_formula(code, env)) - 2.5) < 1e-6


def test_layered_formulas():
    fields = [
        {"uukey": "basic.x", "group": "basic", "field": "x", "ftype": "NUMERIC", "extra": {}},
        {
            "uukey": "basic.a",
            "group": "basic",
            "field": "a",
            "ftype": "NUMERIC",
            "extra": {"formula": "basic.x+1", "depends": ["basic.x"]},
        },
        {
            "uukey": "basic.b",
            "group": "basic",
            "field": "b",
            "ftype": "NUMERIC",
            "extra": {"formula": "basic.a*2", "depends": ["basic.a"]},
        },
    ]
    ensured = ensure_fields_depends(fields)
    b = next(f for f in ensured if f["uukey"] == "basic.b")
    assert "basic.x" in b["extra"]["depends"]
    out = apply_formulas(ensured, {"basic.x": 3})
    assert float(out["basic.a"]) == 4.0
    assert float(out["basic.b"]) == 8.0


def test_ifs_and_if():
    assert float(eval_formula('IFS(1==2, 10, true, 20)', {})) == 20.0
    assert float(eval_formula('IF(3>1, 5, 0)', {})) == 5.0
    env = {"basic": {"tanks": 2}, "mileage": {"national": 100}}
    code = "IFS(basic.tanks==2, mileage.national*0.7, basic.tanks==3, mileage.national*0.8, true, 0)"
    assert abs(float(eval_formula(code, env)) - 70.0) < 1e-6
    env2 = {"goods": {"mileage": 120, "quantity": 1000, "tollFee": 10}}
    freight = (
        "IFS(goods.mileage<=30, goods.quantity*22.5, "
        "goods.mileage<=50, goods.quantity*goods.mileage*0.697, "
        "goods.mileage<=100, goods.quantity*goods.mileage*0.674, "
        "goods.mileage>100, goods.quantity*goods.mileage*IF(goods.tollFee>0, 0.641, 0.639))"
        "/1000+(goods.tollFee*goods.quantity)/1000"
    )
    # 1000*120*0.641/1000 + 10*1000/1000 = 76.92 + 10 = 86.92
    assert abs(float(eval_formula(freight, env2)) - 86.92) < 1e-6


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


def test_api_autofill_freight_energy(client: TestClient):
    _login(client)
    schema = client.post(
        "/api/record/schema",
        json={"model": "freight.energy", "using": "default", "scene": "SEARCH"},
    )
    if schema.status_code != 200:
        pytest.skip("freight.energy not available")
    fields = schema.json()["table"]["fields"]
    total = next((f for f in fields if f.get("uukey") == "basic.total"), None)
    assert total is not None
    assert total.get("extra", {}).get("formula")
    assert "basic.quantity" in (total.get("extra", {}).get("depends") or [])

    res = client.post(
        "/api/record/autofill",
        json={
            "model": "freight.energy",
            "using": "default",
            "value": {"basic.quantity": 10, "basic.price": 2.5},
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert abs(float(data["basic.total"]) - 25.0) < 1e-6
