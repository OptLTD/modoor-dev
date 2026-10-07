"""table.layout normalize + upsert smoke."""

from __future__ import annotations

from builtin.base.domain import CFG_TYPE_TABLE_LAYOUT, normalize_table_layout


def test_normalize_table_layout_nested():
    raw = {
        "fleet.vehicle": {
            "default": {"widths": {"basic.plate": 120, "basic.status": 90, "__action__": 48}},
            "relation": {"basic.plate": 140},
        },
        "bad": "x",
        "fleet.mileage": {
            "default": {"widths": {"basic.uukey": 20}},  # too small → drop
        },
    }
    out = normalize_table_layout(raw)
    assert out["fleet.vehicle"]["default"]["widths"]["basic.plate"] == 120
    assert out["fleet.vehicle"]["default"]["widths"]["__action__"] == 48
    assert out["fleet.vehicle"]["relation"]["widths"]["basic.plate"] == 140
    assert "fleet.mileage" not in out


def test_cfg_type_constant():
    assert CFG_TYPE_TABLE_LAYOUT == "table.layout"
