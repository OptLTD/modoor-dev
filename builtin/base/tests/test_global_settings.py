"""Company global settings: normalize and login landing."""

from __future__ import annotations

from builtin.base.global_settings import landing_module, normalize_global_settings


def test_normalize_keeps_known_values_and_drops_unknown():
    out = normalize_global_settings(
        {
            "locale": "en",
            "timezone": "Asia/Tokyo",
            "timeFormat": "YYYY-MM-DD HH:mm",
            "defaultModule": "freight",
        }
    )
    assert out == {
        "locale": "en-US",
        "timezone": "Asia/Tokyo",
        "timeFormat": "YYYY-MM-DD HH:mm",
        "defaultModule": "freight",
    }
    bad = normalize_global_settings(
        {"locale": "fr", "timezone": "Mars/Base", "timeFormat": "hh:mm", "defaultModule": "../x"}
    )
    assert bad["locale"] == "zh-CN"
    assert bad["timezone"] == "Asia/Shanghai"
    assert bad["timeFormat"] == "YYYY-MM-DD HH:mm:ss"
    assert bad["defaultModule"] == ""


def test_landing_module_respects_permission_and_workbench():
    settings = {"defaultModule": "freight", "locale": "zh-CN", "timezone": "Asia/Shanghai", "timeFormat": "YYYY-MM-DD HH:mm:ss"}
    assert landing_module(settings, enabled={"freight", "base"}, allowed=None) == "freight"
    assert landing_module(settings, enabled={"base"}, allowed=None) is None
    assert landing_module(settings, enabled={"freight"}, allowed={"base"}) is None
    assert landing_module({**settings, "defaultModule": ""}, enabled={"freight"}, allowed=None) is None
