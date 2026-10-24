"""App mobile login and home entries."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from modoor.core.settings import get_settings
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
from modoor.platform.bootstrap import bootstrap
from modoor.testing import configure_test_db
from modoor.web.app import app
from modoor.web.nav import clear_ui_cache


def _freight_tree(root: Path) -> None:
    module = root / "module" / "freight"
    module.mkdir(parents=True)
    module.joinpath("module.yaml").write_text(
        "\n".join(
            [
                "id: freight",
                "version: 0.0.1",
                "actived: true",
                "summary: 货运管理 — 订单、运单、票据、费用、补能",
                "ui-web:",
                "  kind: app",
                "  label: Freight",
                "  base: /freight",
                "  entry: /freight/waybill",
                "i18n:",
                "  zh-CN:",
                "    app.label: 货运管理",
                "exports:",
                "  mobile:",
                "    - id: freight.waybill",
                "      label: 运单",
                "      path: /waybill",
                "      icon: images/tms-waybill.svg",
                "",
            ]
        ),
        encoding="utf-8",
    )
    mobile = root / "mobile" / "freight"
    mobile.mkdir(parents=True)
    mobile.joinpath("package.json").write_text("{}\n", encoding="utf-8")
    ghost = root / "mobile" / "ghost"
    ghost.mkdir(parents=True)
    ghost.joinpath("package.json").write_text("{}\n", encoding="utf-8")


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    _freight_tree(tmp_path)
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
        MODOOR_MODULE_ROOT=str(tmp_path / "module"),
        MODOOR_MODULE_GATE="http://127.0.0.1:8765",
        MODOOR_CAPTCHA_ECHO="1",
        MODOOR_NOTIFY="",
    )
    get_settings.cache_clear()
    clear_ui_cache()
    clear_bundle_cache()
    reload_engine_caches()
    bootstrap()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_mob_login_home_lists_freight(client: TestClient):
    assert client.get("/api/mob/profile").status_code == 401
    assert client.get("/api/mob/home").status_code == 401
    assert client.put("/api/mob/device", json={"device_id": "x"}).status_code == 401

    bad = client.post("/api/mob/login", json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401

    logged = client.post(
        "/api/mob/login", json={"username": "admin", "password": "admin123"}
    )
    assert logged.status_code == 200, logged.text
    body = logged.json()
    assert body["ok"] is True
    assert str(body["user"]["uukey"]).startswith("USER")
    assert "modoor_session" in logged.headers.get("set-cookie", "")

    profile = client.get("/api/mob/profile")
    assert profile.status_code == 200
    assert profile.json()["user"]["uukey"] == body["user"]["uukey"]

    home = client.get("/api/mob/home")
    assert home.status_code == 200, home.text
    groups = home.json()["entries"]
    freight = next(item for item in groups if item["group"] == "货运管理")
    assert freight["intro"] == "货运管理 — 订单、运单、票据、费用、补能"
    waybill = next(item for item in freight["entry"] if item["id"] == "freight.waybill")
    assert waybill["label"] == "运单"
    assert waybill["href"].endswith("/mob/freight/waybill")
    assert waybill["icon"].endswith("/mob/freight/images/tms-waybill.svg")
    assert all(item["group"] != "ghost" for item in groups)

    device = client.put(
        "/api/mob/device",
        json={
            "device_id": "dev-1",
            "model": "Pixel",
            "brand": "Google",
            "system": "Android",
            "version": "14",
        },
    )
    assert device.status_code == 200, device.text
    assert device.json()["device"]["device_id"] == "dev-1"
    assert device.json()["device"]["first_login_at"]

    sent = client.post("/api/mob/captcha", json={"username": "admin"})
    assert sent.status_code == 200, sent.text
    code = sent.json()["dev_code"]
    wrong = client.post("/api/mob/login", json={"username": "admin", "captcha": "000000"})
    assert wrong.status_code == 400
    again = client.post("/api/mob/login", json={"username": "admin", "captcha": code})
    assert again.status_code == 200, again.text
    assert again.json()["ok"] is True
