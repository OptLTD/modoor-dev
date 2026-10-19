from __future__ import annotations

import pytest

from modoor.platform.bootstrap import bootstrap
from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.platform.module_state import list_modules, set_module_enabled, sync_discovered_modules
from modoor.core.settings import get_settings
from builtin.base import domain as base_domain
from builtin.wiki import domain as wiki_domain
from modoor.testing import configure_test_db


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("MODOOR_USER_ID", raising=False)
    monkeypatch.delenv("MODOOR_TEAM_ID", raising=False)
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
    )
    yield
    get_settings.cache_clear()


def test_bootstrap_login_and_module_toggle():
    result = bootstrap(get_settings())
    assert result["admin_username"] == "admin"
    assert result["tenant_id"]
    assert result["team_id"]

    with session_scope() as session:
        tenant_id = result["tenant_id"]
        user = base_domain.authenticate_user(
            session, tenant=tenant_id, username="admin", password="admin123"
        )
        assert user.username == "admin"
        assert user.team_id == result["team_id"]

        with pytest.raises(AppError):
            base_domain.authenticate_user(
                session, tenant=tenant_id, username="admin", password="wrong"
            )

        sync_discovered_modules(session, tenant_id)
        modules = {m["id"]: m for m in list_modules(session, tenant_id)}
        assert modules["base"]["enabled"] is True
        assert "always_on" not in modules["base"] or not modules["base"].get("always_on")

        set_module_enabled(session, tenant_id, "wiki", False)
        modules = {m["id"]: m for m in list_modules(session, tenant_id)}
        assert modules["wiki"]["enabled"] is False

        # base can be disabled (no ALWAYS_ON)
        set_module_enabled(session, tenant_id, "base", False)
        modules = {m["id"]: m for m in list_modules(session, tenant_id)}
        assert modules["base"]["enabled"] is False
        set_module_enabled(session, tenant_id, "base", True)

        # wiki welcome only when wiki enabled — enable for remainder of test
        set_module_enabled(session, tenant_id, "wiki", True)
        from modoor.platform.loader import ensure_module_schema

        ensure_module_schema("wiki")
        ctx = Ctx(tenant=tenant_id, user_id=user.id, team_id=user.team_id)
        projects = wiki_domain.list_projects(session, ctx)
        # may be empty if wiki was off during bootstrap
        if projects["count"] == 0:
            created_proj = wiki_domain.create_project(
                session, ctx, name="General", description="t", home_title="Welcome"
            )
            home_id = created_proj["home_page"]["id"]
        else:
            home_id = projects["items"][0]["home_page_id"]
        assert home_id
        welcome = wiki_domain.get_page(session, ctx, page_id=home_id)
        assert welcome["title"]


def test_bootstrap_strips_quoted_admin_and_uses_superuser_role(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_TENANT='"1001|Acme"',
        MODOOR_ADMIN='"superuser|pass@word"',
    )
    settings = get_settings()
    assert settings.modoor_tenant_id == 1001
    assert settings.modoor_tenant == "Acme"
    assert settings.modoor_admin_username == "superuser"
    assert settings.modoor_admin_password == "pass@word"

    result = bootstrap(settings)
    assert result["admin_username"] == "superuser"
    assert result["tenant_id"] == 1001
    with session_scope() as session:
        user = base_domain.authenticate_user(
            session, tenant=1001, username="superuser", password="pass@word"
        )
        assert user.team_id == result["team_id"]
        ctx = Ctx(tenant=1001, user_id=user.id, team_id=result["team_id"])
        role = base_domain.get_role(session, ctx, code="SUPERUSER")
        assert role["code"] == "SUPERUSER"
        abilities = base_domain.list_user_abilities(session, ctx, user_id=user.id)
        assert abilities["unrestricted"] is False
        selected = base_domain.list_user_abilities(
            session, ctx, user_id=user.id, active_role="SUPERUSER"
        )
        assert selected["unrestricted"] is True


def test_bootstrap_creates_admin_when_tenant_has_no_users():
    settings = get_settings()
    with session_scope() as session:
        ensured = base_domain.ensure_tenant(
            session, settings.modoor_tenant, tenant_id=settings.modoor_tenant_id
        )
        tenant_id = int(ensured["tenant"]["id"])

    result = bootstrap(settings)
    assert result["tenant_id"] == tenant_id
    assert result["created"]["admin_user"] is True

    with session_scope() as session:
        user = base_domain.authenticate_user(
            session, tenant=tenant_id, username="admin", password="admin123"
        )
        assert user.team_id == result["team_id"]


def test_bootstrap_tenant_id_pipe_and_skip_existing(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="1000|Acme",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN="admin|secret123",
    )
    first = bootstrap(get_settings())
    assert first["tenant"] == "Acme"
    assert first["tenant_id"] == 1000
    assert first["created"]["tenant"] is True
    assert first["created"]["root_team"] is True
    assert first["created"]["admin_user"] is True

    with session_scope() as session:
        user = base_domain.authenticate_user(
            session, tenant=1000, username="admin", password="secret123"
        )
        assert user.team_id == first["team_id"]

    second = bootstrap(get_settings())
    assert second["tenant_id"] == 1000
    assert second["created"]["tenant"] is False
    assert second["created"]["root_team"] is False
    assert second["created"]["admin_user"] is False
