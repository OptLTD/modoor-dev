from modoor.engine.project import normalize_field


def test_normalize_field_keeps_alias_list():
    field = normalize_field(
        "items.replace",
        {
            "field": "replace",
            "label": "更换配件",
            "alias": ["更换配件名称", "配件名称", "  ", "更换配件名称"],
        },
    )

    assert field["alias"] == ["更换配件名称", "配件名称"]


def test_normalize_field_accepts_single_alias_string():
    field = normalize_field(
        "basic.total",
        {"field": "total", "label": "费用合计", "alias": "金额"},
    )

    assert field["alias"] == ["金额"]
