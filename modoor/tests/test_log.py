"""Developer logs for business writes."""

from __future__ import annotations

import logging

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.core.log import log, log_delete, log_upsert
from modoor.web.api_util import log_api_error


def test_log_stays_quiet_during_sync(caplog):
    ctx = Ctx(tenant=1, user_id=2, team_id=3, skip_oplog=True)
    with caplog.at_level(logging.INFO, logger="modoor.act"):
        log(ctx, "upsert", model="fleet.freight")
    assert caplog.records == []


def test_log_upsert_names_changed_fields_and_skips_password(caplog):
    ctx = Ctx(tenant=1, user_id=2, team_id=3)
    with caplog.at_level(logging.INFO, logger="modoor.act"):
        log_upsert(
            ctx,
            "fleet.freight",
            [
                {
                    "opType": "UPDATE",
                    "uukey": "F1",
                    "changed": True,
                    "changes": {
                        "goods.freight": {"old": 1, "new": 2},
                        "basic.password": {"old": "a", "new": "b"},
                    },
                }
            ],
        )
        log_delete(ctx, "fleet.mileage", ["M1", "M2"])
    text = " ".join(record.message for record in caplog.records)
    assert "upsert tenant=1 user=2 model=fleet.freight" in text
    assert "UPDATE F1 goods.freight" in text
    assert "password" not in text
    assert "delete tenant=1 user=2 model=fleet.mileage n=2 keys=M1,M2" in text


def test_log_api_error_warns_on_validation_and_traces_bugs(caplog):
    with caplog.at_level(logging.WARNING, logger="modoor.api"):
        log_api_error(AppError("validation_error", "请先勾选"))
    assert caplog.records[-1].levelno == logging.WARNING
    assert "validation_error" in caplog.records[-1].message
    assert "请先勾选" in caplog.records[-1].message

    with caplog.at_level(logging.ERROR, logger="modoor.api"):
        try:
            raise RuntimeError("db down")
        except RuntimeError as exc:
            log_api_error(exc)
    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].exc_info is not None
