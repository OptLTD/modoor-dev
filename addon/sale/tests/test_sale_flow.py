from __future__ import annotations

import json

import pytest

from modoor.runtime.auth import resolve_ctx
from modoor.runtime.confirmation import issue_confirmation_token, verify_confirmation_token
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from addon.sale import domain as sale_domain
from addon.sale.tools import confirm_order, create_order, get_order
from modoor.testing import configure_test_db


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


def test_create_get_confirm_flow():
    created = json.loads(
        create_order(
            partner="Bob",
            lines=[{"product_name": "A", "qty": 1, "unit_price": 9}],
        )
    )
    assert created["status"] == "ok"
    order_id = created["result"]["id"]

    got = json.loads(get_order(order_id))
    assert got["result"]["partner"] == "Bob"

    first = json.loads(confirm_order(order_id=order_id))
    assert first["status"] == "needs_confirmation"
    token = first["confirmation_token"]

    second = json.loads(confirm_order(order_id=order_id, confirmation_token=token))
    assert second["status"] == "ok"
    assert second["result"]["state"] == "confirmed"


def test_confirm_token_args_mismatch():
    settings = get_settings()
    ctx = resolve_ctx(settings)
    with session_scope() as session:
        order = sale_domain.create_order(
            session,
            ctx,
            partner="X",
            lines=[{"product_name": "Y", "qty": 1, "unit_price": 1}],
        )
        order_id = order["id"]

    token, _ = issue_confirmation_token(
        secret=settings.modoor_confirm_secret,
        ctx=ctx,
        tool="sale.confirm_order",
        args={"order_id": order_id},
        ttl_seconds=60,
    )
    with pytest.raises(AppError) as ei:
        verify_confirmation_token(
            secret=settings.modoor_confirm_secret,
            ctx=ctx,
            tool="sale.confirm_order",
            args={"order_id": "other"},
            token=token,
        )
    assert ei.value.code == "validation_error"
