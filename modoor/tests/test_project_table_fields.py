"""视图 fields 是默认显示列，模型其余字段默认隐藏，供列设置使用。"""

from __future__ import annotations

from pathlib import Path

from modoor.engine.project import project_table
from modoor.engine.registry import ModelBundle


def test_table_appends_unlisted_model_fields_as_hidden():
    bundle = ModelBundle(
        uukey="capacity.company",
        module_id="capacity",
        path=Path("."),
        config={
            "model": {"uukey": "capacity.company", "title": "客户"},
            "groups": {
                "basic": {"title": "基础信息", "gtype": "FLATTEN"},
                "account": {"title": "基本存款账户信息", "gtype": "GROUPED"},
            },
            "fields": {
                "basic.uukey": {"field": "uukey", "label": "编号", "seqno": 1, "group": "basic"},
                "basic.name": {"field": "name", "label": "公司名称", "seqno": 2, "group": "basic"},
                "account.name": {
                    "field": "name",
                    "label": "账户名称",
                    "seqno": 40,
                    "group": "account",
                },
            },
            "clicks": {},
        },
        tables={
            "default": {
                "title": "客户信息",
                "fields": ["basic.name", "basic.uukey"],
            }
        },
    )
    table = project_table(bundle, using="default", scene="SEARCH")
    assert table["request"]["order"] == {"field": "basic.utime", "order": "desc"}
    shown = [(f["uukey"], f["shown"]) for f in table["fields"]]
    assert shown == [
        ("basic.name", True),
        ("basic.uukey", True),
        ("account.name", False),
    ]


def test_extra_filter_feeds_table_filters():
    bundle = ModelBundle(
        uukey="freight.order",
        module_id="freight",
        path=Path("."),
        config={
            "model": {"uukey": "freight.order", "title": "订单"},
            "groups": {"basic": {"title": "基础", "gtype": "FLATTEN"}},
            "fields": {
                "basic.uukey": {"field": "uukey", "label": "编号", "seqno": 1, "group": "basic"},
                "basic.utime": {
                    "field": "utime",
                    "label": "下单时间",
                    "ftype": "DATETIME",
                    "seqno": 2,
                    "group": "basic",
                },
            },
            "clicks": {},
        },
        tables={
            "recent": {
                "title": "订单列表",
                "extra": {"filter": ["basic.utime", "basic.uukey"]},
                "order": {"field": "basic.uukey", "order": "asc"},
            }
        },
    )
    table = project_table(bundle, using="recent", scene="SEARCH")
    assert table["filters"] == ["basic.utime", "basic.uukey"]
    assert table["request"]["order"] == {"field": "basic.uukey", "order": "asc"}

    ordered = project_table(
        bundle,
        using="recent",
        scene="SEARCH",
        order={"field": "basic.utime", "order": "desc"},
    )
    assert ordered["request"]["order"] == {"field": "basic.utime", "order": "desc"}
