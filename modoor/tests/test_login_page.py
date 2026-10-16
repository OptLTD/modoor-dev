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
        MODOOR_ADMIN_USERNAME="superuser",
        MODOOR_ADMIN_PASSWORD="pass@word",
        MODOOR_CAPTCHA_ECHO="1",
    )
    get_settings.cache_clear()
    clear_ui_cache()
    clear_bundle_cache()
    reload_engine_caches()
    bootstrap()
    # Avoid MCP lifespan: session_manager.run() can only start once per process.
    client = TestClient(app)
    yield client
    get_settings.cache_clear()


def _cookies(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def test_login_page_is_split_layout(client: TestClient):
    page = client.get("/login")
    assert page.status_code == 200
    assert "login-view.webm" in page.text
    assert "记住我" in page.text
    assert "验证码登录" in page.text
    asset = client.get("/login/assets/login-view.webm")
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("video/webm")
    assert client.get("/login/assets/nope.png").status_code == 404


def test_password_login_and_remember_cookie(client: TestClient):
    bad = client.post(
        "/login",
        data={"username": "admin", "password": "nope"},
        follow_redirects=False,
    )
    assert bad.status_code == 400
    assert "用户名或密码错误" in bad.text

    remembered = client.post(
        "/login",
        data={"username": "superuser", "password": "pass@word", "remember": "on"},
        follow_redirects=False,
    )
    assert remembered.status_code == 303
    cookies = _cookies(remembered)
    assert any(item.startswith("modoor_remember=") and "Max-Age=0" not in item for item in cookies)
    session = next(item for item in cookies if item.startswith("modoor_session="))
    assert "max-age=" in session.lower()

    client.cookies.delete("modoor_session")
    home = client.get("/home")
    assert "/login" not in str(home.url)


def test_login_without_remember_is_browser_session(client: TestClient):
    res = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    cookies = _cookies(res)
    session = next(item for item in cookies if item.startswith("modoor_session="))
    assert "max-age=" not in session.lower()
    remember = [item for item in cookies if item.startswith("modoor_remember=")]
    assert remember
    assert "max-age=0" in remember[0].lower()

    client.cookies.delete("modoor_session")
    home = client.get("/home", follow_redirects=False)
    assert home.status_code == 303
    assert "/login" in home.headers["location"]


def test_captcha_login_and_rate_limit(client: TestClient):
    missing = client.post("/login/captcha", json={"username": "nobody"})
    assert missing.status_code == 404
    assert "dev_code" not in missing.json()

    sent = client.post("/login/captcha", json={"username": "admin"})
    assert sent.status_code == 200
    code = sent.json()["dev_code"]
    assert len(code) == 6

    again = client.post("/login/captcha", json={"username": "admin"})
    assert again.status_code == 429

    bad = client.post(
        "/login",
        data={"username": "admin", "auth_type": "captcha", "captcha": "000000"},
        follow_redirects=False,
    )
    assert bad.status_code == 400
    assert "验证码错误" in bad.text

    good = client.post(
        "/login",
        data={"username": "admin", "auth_type": "captcha", "captcha": code, "remember": "on"},
        follow_redirects=False,
    )
    assert good.status_code == 303

    reused = client.post(
        "/login",
        data={"username": "admin", "auth_type": "captcha", "captcha": code},
        follow_redirects=False,
    )
    assert reused.status_code == 400
    assert "请先获取验证码" in reused.text


def test_logout_clears_remember_cookie(client: TestClient):
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "remember": "on"},
        follow_redirects=False,
    )
    out = client.post("/logout", follow_redirects=False)
    assert out.status_code == 303
    cleared = _cookies(out)
    assert any(
        item.startswith("modoor_remember=") and "max-age=0" in item.lower() for item in cleared
    )
    client.cookies.clear()
    home = client.get("/home", follow_redirects=False)
    assert home.status_code == 303
    assert "/login" in home.headers["location"]


def test_profile_page_and_self_password(client: TestClient):
    guest = client.get("/profile", follow_redirects=False)
    assert guest.status_code == 303
    assert "/login" in guest.headers["location"]

    logged = client.post(
        "/login",
        data={"username": "superuser", "password": "pass@word"},
        follow_redirects=False,
    )
    assert logged.status_code == 303
    page = client.get("/profile")
    assert page.status_code == 200
    assert "个人中心" in page.text
    assert "修改密码" in page.text
    assert "验证码" in page.text
    assert 'class="profile-left"' in page.text
    assert 'class="profile-right"' in page.text
    assert 'class="legal-notice"' in page.text
    assert 'class="profile-table-wrap"' in page.text

    empty = client.post("/api/auth/password", json={"password": "  "})
    assert empty.status_code == 400
    missing = client.post("/api/auth/password", json={"password": "admin123"})
    assert missing.status_code == 400
    sent = client.post("/login/captcha", json={"username": "superuser"})
    assert sent.status_code == 200
    code = sent.json()["dev_code"]
    ok = client.post("/api/auth/password", json={"password": "admin123", "captcha": code})
    assert ok.status_code == 200
    assert ok.json().get("ok") is True


def test_captcha_is_not_echoed_when_disabled(client: TestClient, monkeypatch):
    monkeypatch.setenv("MODOOR_CAPTCHA_ECHO", "0")
    get_settings.cache_clear()
    res = client.post("/login/captcha", json={"username": "admin"})
    assert res.status_code == 400
    assert "dev_code" not in res.json()
    assert "无法发送" in res.json()["error"]
