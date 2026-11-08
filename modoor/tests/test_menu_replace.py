"""Host menu overrides declared in module.yaml replace."""

from __future__ import annotations

from pathlib import Path

import yaml

from modoor.web.mount import join_web_mount
from modoor.web.nav import (
    _mount_replace,
    _normalize_replace,
    filter_menus_by_industry,
    mark_blend_listing,
    merge_blended_menus,
)

FREIGHT_YAML = Path(__file__).resolve().parents[3] / "modoor-pro" / "module" / "freight" / "module.yaml"


def test_replace_null_removes_and_object_patches_path():
    raw = {
        "fleet.home": {"path": "/freight/home"},
        "fleet.report": {"path": "/freight/report", "items": []},
        "fleet.haulage": None,
    }
    norm = _normalize_replace(raw, mid="freight")
    assert norm["fleet.haulage"] is None
    assert norm["fleet.home"] == {"path": "/freight/home"}
    assert norm["fleet.report"]["path"] == "/freight/report"
    assert norm["fleet.report"]["items"] == []

    mounted = _mount_replace(norm, join_web_mount)
    assert mounted["fleet.home"]["path"] == "/mod/freight/home"
    assert mounted["fleet.report"]["path"] == "/mod/freight/report"
    assert mounted["fleet.report"]["items"] == []
    assert mounted["fleet.haulage"] is None


def test_industry_filter_keeps_untagged_and_drops_empty_groups():
    menus = [
        {"id": "fleet.home", "path": "/fleet/home"},
        {"id": "fleet.report", "path": "/fleet/report", "industry": ["fuel"]},
        {
            "id": "fleet.haulage",
            "items": [
                {"id": "fleet.import", "path": "/fleet/import", "industry": ["fuel"]},
                {"id": "fleet.mileage", "path": "/fleet/mileage"},
            ],
        },
    ]
    fuel = [item["id"] for item in filter_menus_by_industry(menus, "fuel")]
    bulk = filter_menus_by_industry(menus, "bulk")
    assert fuel == ["fleet.home", "fleet.report", "fleet.haulage"]
    assert [item["id"] for item in bulk] == ["fleet.home", "fleet.haulage"]
    assert [item["id"] for item in bulk[1]["items"]] == ["fleet.mileage"]
    assert [item["id"] for item in filter_menus_by_industry(menus, "all")] == [
        "fleet.home",
        "fleet.report",
        "fleet.haulage",
    ]


def test_freight_module_replace_rewrites_settings_group():
    data = yaml.safe_load(FREIGHT_YAML.read_text(encoding="utf-8"))
    norm = _normalize_replace(data.get("replace"), mid="freight")
    assert set(norm) == {"fleet.home", "fleet.report", "fleet.haulage", "fleet.setting"}
    assert norm["fleet.haulage"] is None
    assert norm["fleet.home"]["path"] == "/freight/home"
    assert norm["fleet.report"]["path"] == "/freight/report"
    assert norm["fleet.report"]["items"] == []
    setting_ids = [item["id"] for item in norm["fleet.setting"]["items"]]
    assert setting_ids == ["fleet.setting.main", "fleet.fields", "freight.waybill.setup"]


def test_catalog_merge_applies_replace_before_industry_filter():
    data = yaml.safe_load(FREIGHT_YAML.read_text(encoding="utf-8"))
    replace = _mount_replace(_normalize_replace(data.get("replace"), mid="freight"), join_web_mount)
    fleet = {
        "id": "fleet",
        "i18n": {"zh-CN": {"fleet.setting": "系统设置"}},
        "menus": [
            {"id": "fleet.home", "label": "Dashboard", "path": "/mod/fleet/home", "seqno": 5},
            {
                "id": "fleet.report",
                "label": "Reports",
                "path": "/mod/fleet/report",
                "seqno": 15,
                "industry": ["fuel"],
                "items": [{"id": "fleet.report.vehicle_cost", "label": "Vehicle cost"}],
            },
            {
                "id": "fleet.haulage",
                "label": "Haulage",
                "seqno": 20,
                "items": [{"id": "fleet.mileage", "label": "Mileage", "path": "/mod/fleet/mileage"}],
            },
            {
                "id": "fleet.setting",
                "label": "System settings",
                "seqno": 50,
                "items": [
                    {
                        "id": "fleet.setting.main",
                        "label": "System settings",
                        "path": "/mod/fleet/setting",
                        "seqno": 10,
                    }
                ],
            },
        ],
    }
    freight = {
        "id": "freight",
        "blend": "fleet",
        "replace": replace,
        "i18n": {"zh-CN": {"freight.waybill.setup": "运单设置"}},
        "menus": [
            {
                "id": "freight.order",
                "label": "Orders",
                "path": "/mod/freight/order",
                "seqno": 20,
                "industry": ["bulk"],
            }
        ],
    }
    merged = merge_blended_menus([fleet, freight])
    fleet_menus = merged[0]["menus"]
    assert [item["id"] for item in fleet_menus] == [item["id"] for item in merged[1]["menus"]]
    assert "fleet.haulage" not in [item["id"] for item in fleet_menus]
    home = next(item for item in fleet_menus if item["id"] == "fleet.home")
    assert home["path"] == "/mod/freight/home"
    setting = next(item for item in fleet_menus if item["id"] == "fleet.setting")
    assert [item["id"] for item in setting["items"]][-1] == "freight.waybill.setup"
    assert merged[0]["i18n"]["zh-CN"]["freight.waybill.setup"] == "运单设置"
    assert merged[1]["i18n"]["zh-CN"]["fleet.setting"] == "系统设置"

    listed = mark_blend_listing(merged)
    assert listed[0]["listed"] is False
    assert listed[0]["shell"] == "freight"
    assert listed[0].get("blend") is None
    assert listed[1]["listed"] is True
    assert "shell" not in listed[1]

    fuel = filter_menus_by_industry(fleet_menus, "fuel")
    fuel_ids = [item["id"] for item in fuel]
    assert "freight.order" not in fuel_ids
    fuel_setting = next(item for item in fuel if item["id"] == "fleet.setting")
    assert [item["id"] for item in fuel_setting["items"]] == ["fleet.setting.main", "fleet.fields"]


def test_blended_guest_inherits_host_permission(monkeypatch):
    """A role that may open the host also keeps the blended guest in the shell."""
    from inbuilt.base import domain as base_domain

    monkeypatch.setattr(
        base_domain,
        "list_user_abilities",
        lambda *args, **kwargs: {
            "unrestricted": False,
            "abilities": ["fleet.home.list"],
        },
    )
    monkeypatch.setattr(
        "modoor.platform.module_state.blend_guest_map",
        lambda *args, **kwargs: {"freight": "fleet"},
    )

    visible = base_domain.allowed_modules_for_user(
        None,
        None,
        user_id=1,
        enabled={"fleet", "freight", "doc"},
    )

    assert visible == {"fleet", "freight"}
