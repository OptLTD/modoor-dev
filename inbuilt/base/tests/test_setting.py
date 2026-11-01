"""Company global settings: normalize and login landing."""

from __future__ import annotations

from inbuilt.base.setting import (
    env_map_settings,
    landing_module,
    normalize_map_settings,
    normalize_menu_layouts,
    normalize_settings,
)
from modoor.core.settings import get_settings


def test_normalize_keeps_known_values_and_drops_unknown():
    out = normalize_settings(
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
    bad = normalize_settings(
        {"locale": "fr", "timezone": "Mars/Base", "timeFormat": "hh:mm", "defaultModule": "../x"}
    )
    assert bad["locale"] == "zh-CN"
    assert bad["timezone"] == "Asia/Shanghai"
    assert bad["timeFormat"] == "YYYY-MM-DD HH:mm:ss"
    assert bad["defaultModule"] == ""


def test_map_settings_keep_provider_and_tokens():
    out = normalize_map_settings(
        {"provider": "AMAP", "token1": " key-1 ", "token2": "key-2"}
    )
    assert out == {"provider": "amap", "token1": "key-1", "token2": "key-2"}

    bad = normalize_map_settings(
        {"provider": "../evil", "token1": None, "token2": 123}
    )
    assert bad == {"provider": "tianditu", "token1": "", "token2": "123"}


def test_env_map_settings_use_three_keys(monkeypatch):
    monkeypatch.setenv("MODOOR_MAP_PROVIDER", "AMAP")
    monkeypatch.setenv("MODOOR_MAP_TOKEN1", " key-1 ")
    monkeypatch.setenv("MODOOR_MAP_TOKEN2", "")
    get_settings.cache_clear()
    try:
        assert env_map_settings() == {
            "provider": "amap",
            "token1": "key-1",
            "token2": "",
        }
    finally:
        get_settings.cache_clear()


def test_menu_layout_keeps_side_and_drops_top():
    assert normalize_menu_layouts({"fleet": "side", "base": "top", "../x": "side"}) == {
        "fleet": "side"
    }
    assert normalize_menu_layouts(None) == {}


def test_landing_module_respects_permission_and_workbench():
    settings = {"defaultModule": "freight", "locale": "zh-CN", "timezone": "Asia/Shanghai", "timeFormat": "YYYY-MM-DD HH:mm:ss"}
    assert landing_module(settings, enabled={"freight", "base"}, allowed=None) == "freight"
    assert landing_module(settings, enabled={"base"}, allowed=None) is None
    assert landing_module(settings, enabled={"freight"}, allowed={"base"}) is None
    assert landing_module({**settings, "defaultModule": ""}, enabled={"freight"}, allowed=None) is None
