"""关联选择器列头：sticky 字段带可读 label。"""

from __future__ import annotations

from modoor.engine.project import project_table
from modoor.engine.registry import get_bundle
from modoor.engine.service import _related_header


def test_related_header_uses_sticky_labels():
    table = project_table(get_bundle("fleet.vehicle"), using="default", scene="SEARCH")
    header = _related_header(table)
    assert header
    by_key = {h["uukey"]: h["label"] for h in header}
    assert by_key.get("basic.plate") == "车牌号码"
    assert by_key.get("basic.uukey") == "车辆编号"
