"""Tests for base.oplog audit recording (model field diffs)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx
from modoor.testing import configure_test_db
from builtin.base.adapters import SystemUserAdapter
from builtin.base.domain import SystemOplog, diff_row_values, list_record_oplogs, record_oplog


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="t1",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
    )
    get_settings.cache_clear()
    bootstrap()
    yield
    get_settings.cache_clear()


def test_diff_row_values_skips_noise_and_detects_change():
    before = {"basic.name": "A", "basic.utime": "t1", "basic.password": "x"}
    after = {"basic.name": "B", "basic.utime": "t2", "basic.password": "y"}
    diff = diff_row_values(before, after)
    assert "basic.name" in diff
    assert diff["basic.name"] == {"old": "A", "new": "B"}
    assert "basic.utime" not in diff
    assert "basic.password" not in diff


def test_record_oplog_and_user_upsert_writes_audit():
    ctx = resolve_ctx(get_settings())
    adapter = SystemUserAdapter()
    with session_scope() as session:
        recs = adapter.upsert(
            session,
            ctx,
            [{"basic.email": "oplog@example.com", "basic.name": "Oplog User"}],
        )
        assert recs[0]["opType"] == "INSERT"
        assert recs[0]["changes"]
        code = recs[0]["uukey"]
        rows = session.scalars(
            select(SystemOplog).where(
                SystemOplog.tenant == ctx.tenant,
                SystemOplog.code == code,
                SystemOplog.action == "INSERT",
            )
        ).all()
        assert len(rows) >= 1
        payload = rows[-1].values
        assert rows[-1].model == "base.user"
        assert payload["model"] == "base.user"
        assert "basic.name" in payload["diff"]

        recs2 = adapter.upsert(
            session,
            ctx,
            [{"basic.code": code, "basic.name": "Oplog Renamed"}],
        )
        assert recs2[0]["opType"] == "UPDATE"
        assert "basic.name" in recs2[0]["changes"]
        upd = session.scalars(
            select(SystemOplog).where(
                SystemOplog.tenant == ctx.tenant,
                SystemOplog.code == code,
                SystemOplog.action == "UPDATE",
            )
        ).all()
        assert len(upd) >= 1
        assert upd[-1].values["diff"]["basic.name"]["new"] == "Oplog Renamed"


def test_skip_oplog_flag():
    ctx = resolve_ctx(get_settings())
    quiet = Ctx(
        tenant=ctx.tenant,
        user_id=ctx.user_id,
        team_id=ctx.team_id,
        skip_oplog=True,
    )
    with session_scope() as session:
        c0 = session.scalar(
            select(func.count()).select_from(SystemOplog).where(SystemOplog.tenant == ctx.tenant)
        )
        out = record_oplog(
            session,
            quiet,
            code="X",
            action="INSERT",
            model="fleet.vehicle",
            after={"basic.plate": "A"},
        )
        assert out is None
        c1 = session.scalar(
            select(func.count()).select_from(SystemOplog).where(SystemOplog.tenant == ctx.tenant)
        )
        assert c1 == c0


def test_list_record_oplogs_filters_by_model():
    ctx = resolve_ctx(get_settings())
    with session_scope() as session:
        record_oplog(
            session,
            ctx,
            code="LIST-OP-1",
            action="INSERT",
            model="fleet.vehicle",
            after={"basic.plate": "A"},
        )
        record_oplog(
            session,
            ctx,
            code="LIST-OP-1",
            action="UPDATE",
            model="fleet.trailer",
            before={"basic.plate": "T1"},
            after={"basic.plate": "T2"},
        )
        vehicle_logs = list_record_oplogs(
            session, ctx, code="LIST-OP-1", model="fleet.vehicle"
        )
        assert len(vehicle_logs) == 1
        assert vehicle_logs[0]["action"] == "INSERT"
        assert vehicle_logs[0]["model"] == "fleet.vehicle"
        all_logs = list_record_oplogs(session, ctx, code="LIST-OP-1")
        assert len(all_logs) == 2
