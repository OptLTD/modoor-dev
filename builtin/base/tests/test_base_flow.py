from __future__ import annotations

import pytest

from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import get_settings
from builtin.base.adapters import SystemUserAdapter
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx
from modoor.testing import configure_test_db
from builtin.base import domain as base_domain


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="t1",
        MODOOR_CONFIRM_SECRET="secret",
    )
    bootstrap(get_settings())
    yield
    get_settings.cache_clear()


def test_user_role_assign():
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        user = base_domain.create_user(
            session, ctx, username="Alice", realname="Alice Chen", password="pw"
        )
        assert user["username"] == "alice"
        user_id = user["id"]

        role = base_domain.create_role(session, ctx, name="Ops Lead")
        role_id = role["id"]
        assert str(role["code"]).startswith("role")

        base_domain.assign_role(session, ctx, user_id=user_id, role_id=role_id)
        roles = base_domain.list_user_roles(session, ctx, user_id=user_id)
        assert roles["count"] == 1
        assert roles["roles"][0]["id"] == role_id


def test_teams_hang_under_head():
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        head = base_domain.root_team_id(session, ctx.tenant)
        sales = base_domain.create_team(session, ctx, name="Sales", parent=None)
        assert sales["parent"] == head
        ops = base_domain.create_team(session, ctx, name="Ops", parent=sales["id"])
        assert ops["parent"] == head
        with pytest.raises(AppError) as ei:
            base_domain.update_team(session, ctx, team_id=ops["id"], parent=sales["id"])
        assert ei.value.code == "validation_error"
        with pytest.raises(AppError) as ei:
            base_domain.update_team(session, ctx, team_id=ops["id"], parent=None)
        assert ei.value.code == "validation_error"
        with pytest.raises(AppError) as ei:
            base_domain.update_team(session, ctx, team_id=head, parent=sales["id"])
        assert ei.value.code == "validation_error"

        tree = base_domain.list_team_tree(session, ctx)
        assert tree["count"] >= 3
        assert len(tree["tree"]) == 1
        assert tree["tree"][0]["id"] == head
        child_ids = {c["id"] for c in tree["tree"][0]["children"]}
        assert sales["id"] in child_ids
        assert ops["id"] in child_ids


def test_user_upsert_without_password_and_cannot_self_disable():
    ctx = resolve_ctx(get_settings())
    adapter = SystemUserAdapter()
    with session_scope() as session:
        recs = adapter.upsert(
            session,
            ctx,
            [{"basic.email": "nopw@example.com", "basic.name": "No Password"}],
        )
        assert recs[0]["opType"] == "INSERT"
        uukey = recs[0]["uukey"]
        assert str(uukey).startswith("USER")
        assert recs[0]["current"]["basic.email"] == "nopw@example.com"
        with pytest.raises(AppError) as ei:
            base_domain.update_user(session, ctx, user_id=ctx.user_id, active=False)
        assert ei.value.code == "validation_error"
        out = base_domain.update_user(session, ctx, uukey=uukey, active=False)
        assert out["active"] is False
        assert out["enable"] == 0
        assert out["state"] == 1
        out = base_domain.update_user(session, ctx, uukey=uukey, password="secret")
        assert out["uukey"] == uukey


def test_login_shared_across_tenants():
    from modoor.core.ctx import Ctx

    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        other = base_domain.ensure_tenant(session, "t2")
        ctx2 = Ctx(
            tenant=other["tenant"]["id"],
            user_id=0,
            team_id=other["team"]["id"],
        )
        u1 = base_domain.create_user(
            session, ctx, username="shared", realname="A", password="pw"
        )
        u2 = base_domain.create_user(
            session, ctx2, username="shared", realname="B", password="pw"
        )
        assert u1["base_id"] == u2["base_id"]
        u1 = base_domain.get_user(session, ctx, user_id=u1["id"])
        assert u1["realname"] == "B"
        assert u2["realname"] == "B"
        a1 = base_domain.authenticate_user(
            session, tenant=ctx.tenant, username="shared", password="pw"
        )
        a2 = base_domain.authenticate_user(
            session, tenant=ctx2.tenant, username="shared", password="pw"
        )
        assert a1.id == u1["id"]
        assert a2.id == u2["id"]
        assert a1.uukey != a2.uukey
        assert a1.realname == a2.realname == "B"
        assert a2.current == ctx2.tenant
        a1 = base_domain.authenticate_user(
            session, tenant=ctx.tenant, username="shared", password="pw"
        )
        assert a1.current == ctx.tenant


def test_create_user_binds_login_from_email_or_phone():
    from modoor.core.ctx import Ctx
    from modoor.core.security import verify_password
    from builtin.base.domain import SystemLogin

    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        with pytest.raises(AppError) as ei:
            base_domain.create_user(session, ctx, name="No Contact")
        assert ei.value.code == "validation_error"

        by_mail = base_domain.create_user(
            session, ctx, name="Mail User", email="Mail.User@Example.com"
        )
        assert by_mail["username"] == "mail.user@example.com"
        assert by_mail["realname"] == "Mail User"
        assert by_mail["email"] == "Mail.User@Example.com"

        by_phone = base_domain.create_user(
            session, ctx, name="Phone User", phone="13800138000", password="phone-pw"
        )
        assert by_phone["username"] == "13800138000"

        first = base_domain.create_user(
            session, ctx, name="Shared Mail", email="join@example.com", password="old"
        )
        other = base_domain.ensure_tenant(session, "t-mail")
        ctx2 = Ctx(
            tenant=other["tenant"]["id"],
            user_id=0,
            team_id=other["team"]["id"],
        )
        linked = base_domain.create_user(
            session,
            ctx2,
            name="Other Name",
            email="join@example.com",
            password="new",
        )
        assert linked["base_id"] == first["base_id"]
        assert linked["realname"] == "Other Name"
        login = session.get(SystemLogin, first["base_id"])
        assert login is not None
        assert login.realname == "Other Name"
        assert verify_password("old", login.password)

        updated = base_domain.update_user(
            session, ctx, uukey=first["uukey"], name="Renamed", password="new"
        )
        session.refresh(login)
        assert updated["name"] == "Renamed"
        assert login.realname == "Renamed"
        assert verify_password("new", login.password)


def test_tenant_rejects_duplicate_email_or_phone():
    from modoor.core.ctx import Ctx

    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        base_domain.create_user(
            session, ctx, name="One", email="dup@example.com", phone="13900001111"
        )
        with pytest.raises(AppError) as ei:
            base_domain.create_user(
                session, ctx, name="Two", email="DUP@example.com"
            )
        assert ei.value.code == "conflict"
        with pytest.raises(AppError) as ei:
            base_domain.create_user(
                session, ctx, name="Three", phone="13900001111"
            )
        assert ei.value.code == "conflict"

        other = base_domain.create_user(
            session, ctx, name="Four", email="other@example.com", phone="13900002222"
        )
        with pytest.raises(AppError) as ei:
            base_domain.update_user(
                session, ctx, uukey=other["uukey"], email="dup@example.com"
            )
        assert ei.value.code == "conflict"
        with pytest.raises(AppError) as ei:
            base_domain.update_user(
                session, ctx, uukey=other["uukey"], phone="13900001111"
            )
        assert ei.value.code == "conflict"

        tenant2 = base_domain.ensure_tenant(session, "t-dup")
        ctx2 = Ctx(
            tenant=tenant2["tenant"]["id"],
            user_id=0,
            team_id=tenant2["team"]["id"],
        )
        copied = base_domain.create_user(
            session, ctx2, name="Other Tenant", email="dup@example.com", phone="13900001111"
        )
        assert copied["email"] == "dup@example.com"

