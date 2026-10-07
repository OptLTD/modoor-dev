"""Digest / pivot table views: group → count → append(+total).

Aligned with option-duolali DigestService string formats:

- group: ``index|sort[|format]``  (format: date|month)
- count: ``index|func[|label]``   (CNT|SUM|AVG|MAX|MIN|UNQ)
- append: ``field|label[|ftype|formula]`` → synthetic ``append.{field}``
- ``total(label_or_key)`` in append formula = grand-total row value
"""

from __future__ import annotations

import ast
import copy
import math
import re
from typing import Any

from modoor.engine.formula import (
    _SafeEval,
    _flat_to_objects,
    _set_path,
    _write_formula_result,
    formula_text,
)


def is_digest_view(others: dict[str, Any] | None) -> bool:
    if not isinstance(others, dict):
        return False
    group = others.get("group")
    count = others.get("count")
    return bool(group) and bool(count)


def _as_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        s = str(item or "").strip()
        if s:
            out.append(s)
    return out


def parse_group_by(raw: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_str_list(raw):
        parts = item.split("|")
        entry = {"index": parts[0].strip(), "sort": "ASC", "format": ""}
        if len(parts) >= 2 and parts[1].strip():
            entry["sort"] = parts[1].strip().upper()
        if len(parts) >= 3 and parts[2].strip():
            entry["format"] = parts[2].strip().lower()
        if entry["index"]:
            result.append(entry)
    return result


def parse_count_fn(raw: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_str_list(raw):
        parts = item.split("|")
        entry = {"index": parts[0].strip(), "func": "SUM", "label": ""}
        if len(parts) >= 2 and parts[1].strip():
            entry["func"] = parts[1].strip().upper()
        if len(parts) >= 3 and parts[2].strip():
            entry["label"] = parts[2].strip()
        if entry["index"]:
            result.append(entry)
    return result


def parse_append(raw: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_str_list(raw):
        parts = item.split("|")
        if len(parts) < 2:
            continue
        entry = {
            "field": parts[0].strip(),
            "label": parts[1].strip(),
            "ftype": "NUMERIC",
            "formula": "",
        }
        if len(parts) >= 3 and parts[2].strip():
            entry["ftype"] = parts[2].strip()
        if len(parts) >= 4 and parts[3].strip():
            entry["formula"] = parts[3].strip()
        if entry["field"]:
            result.append(entry)
    return result


def parse_pivot(raw: Any) -> dict[str, str] | None:
    s = str(raw or "").strip()
    if not s:
        return None
    parts = s.split("|")
    if len(parts) < 2:
        return None
    state = parts[2].strip().lower() if len(parts) >= 3 else "on"
    if state in ("none", "off", ""):
        return None
    return {"pivot": parts[0].strip(), "value": parts[1].strip(), "state": state}


_TOTAL_CALL_RE = re.compile(r"\btotal\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)


def rebuild_append_formula(code: str, label_aliases: dict[str, str]) -> str:
    """Replace Chinese labels with field keys; keep total(path) as attribute path."""
    out = str(code or "").strip()
    if not out:
        return ""
    for label in sorted(label_aliases.keys(), key=len, reverse=True):
        key = label_aliases[label]
        if not label or not key or label == key:
            continue
        out = out.replace(label, key)

    def _norm_total(m: re.Match[str]) -> str:
        inner = m.group(1).strip().strip("\"'")
        return f"total({inner})"

    return _TOTAL_CALL_RE.sub(_norm_total, out)


def _attr_path(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _attr_path(node.value)
        if not base:
            return None
        return f"{base}.{node.attr}"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class _DigestEval(_SafeEval):
    """Formula eval with total(path) reading grand-total objects."""

    def __init__(self, env: dict[str, Any], totals_env: dict[str, Any] | None = None):
        super().__init__(env)
        self.totals_env = totals_env or {}

    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Name) and node.func.id.lower() == "total":
            if len(node.args) != 1:
                raise ValueError("total expects 1 arg")
            path = _attr_path(node.args[0])
            if not path:
                val = self.visit(node.args[0])
                path = str(val or "").strip()
            return _lookup_path(self.totals_env, path)
        return super().visit_Call(node)


def _lookup_path(objects: dict[str, Any], path: str) -> Any:
    if not path:
        return 0
    if path in objects:
        v = objects.get(path)
        return 0 if v in (None, "") else v
    parts = [p for p in path.split(".") if p]
    cur: Any = objects
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return 0
        cur = cur[p]
    if cur is None or cur == "":
        return 0
    return cur


def eval_append_formula(
    code: str,
    row_objects: dict[str, Any],
    totals_objects: dict[str, Any],
) -> Any:
    tree = ast.parse(code, mode="eval")
    return _DigestEval(row_objects, totals_objects).visit(tree)


def project_digest_table(
    bundle: Any,
    *,
    using: str,
    view: dict[str, Any],
    others: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], dict[str, Any]]:
    """Build digest fields / sticky / groups / parse meta from table view."""
    from modoor.engine.project import normalize_field

    group_by = parse_group_by(others.get("group"))
    count_fn = parse_count_fn(others.get("count"))
    appends = parse_append(others.get("append"))
    pivot = parse_pivot(others.get("pivot"))

    groups_meta = bundle.groups
    all_fields = {
        k: normalize_field(
            k,
            bundle.fields[k],
            group_meta=groups_meta.get(str(bundle.fields[k].get("group") or "")),
        )
        for k in bundle.fields
    }

    shown: list[dict[str, Any]] = []
    sticky: list[str] = []
    seen: set[str] = set()

    for i, g in enumerate(group_by):
        key = g["index"]
        src = all_fields.get(key)
        if not src:
            continue
        f = copy.deepcopy(src)
        f["shown"] = True
        f["seqno"] = i - 100
        shown.append(f)
        sticky.append(key)
        seen.add(key)

    label_aliases: dict[str, str] = {}
    for f in all_fields.values():
        lab = str(f.get("label") or "").replace("|", "").strip()
        key = str(f.get("uukey") or "").strip()
        if lab and key:
            label_aliases[lab] = key

    for i, c in enumerate(count_fn):
        key = c["index"]
        src = all_fields.get(key)
        if not src:
            continue
        f = copy.deepcopy(src)
        f["shown"] = True
        f["seqno"] = i
        fn = str(c.get("func") or "SUM").upper()
        # 度量列一律按数字展示：右对齐、不可点进详情
        f["ftype"] = "INTEGER" if fn in ("CNT", "UNQ") else "NUMERIC"
        extra = dict(f.get("extra") or {})
        extra["editable"] = "NEVER"
        extra["navigable"] = False
        if fn in ("CNT", "UNQ"):
            extra["precision"] = 0
        elif extra.get("precision") is None:
            extra["precision"] = 2
        # 避免 SERIALNO/uukey 被前端当成主键跳转
        if str(f.get("field") or "") == "uukey" or str(f.get("ftype") or "").upper() == "SERIALNO":
            f["field"] = "cnt" if fn in ("CNT", "UNQ") else str(key.split(".")[-1] or "metric")
        f["extra"] = extra
        if c["label"]:
            f["label"] = c["label"]
            label_aliases[c["label"]] = key
        if key not in seen:
            shown.append(f)
            seen.add(key)
        else:
            for j, existing in enumerate(shown):
                if existing.get("uukey") == key:
                    shown[j] = f
                    break

    groups_out = [
        {
            **copy.deepcopy(g),
            "uukey": gk,
            "model": g.get("model") or bundle.uukey,
        }
        for gk, g in sorted(
            groups_meta.items(),
            key=lambda kv: int((kv[1] or {}).get("seqno") or 0),
        )
    ]
    if appends and not any(g.get("uukey") == "append" for g in groups_out):
        groups_out.append(
            {
                "uukey": "append",
                "title": "扩展字段",
                "gtype": "GROUPED",
                "model": bundle.uukey,
                "seqno": 900,
                "extra": {},
            }
        )

    start = len(shown)
    for j, ap in enumerate(appends):
        key = f"append.{ap['field']}"
        formula = rebuild_append_formula(ap["formula"], label_aliases)
        if ap["label"]:
            label_aliases[ap["label"]] = key
        # rebuild again so later append labels can reference earlier append labels
        formula = rebuild_append_formula(ap["formula"], label_aliases)
        label = ap["label"] or ap["field"]
        extra: dict[str, Any] = {
            "formula": formula,
            "display": ap["formula"],
            "aggrType": "recalc",
            "editable": "NEVER",
            "navigable": False,
            "precision": 2,
        }
        # 占比/率类扩展列默认按 percent 展示
        if "%" in label or any(
            x in str(ap["field"]).lower()
            for x in ("rate", "ratio", "percent", "pct")
        ):
            extra["valueFmt"] = "percent"
        f = {
            "uukey": key,
            "index": key,
            "field": ap["field"],
            "group": "append",
            "gname": "扩展字段",
            "label": label,
            "ftype": ap["ftype"] or "NUMERIC",
            "shown": True,
            "seqno": start + j,
            "extra": extra,
        }
        shown.append(f)

    shown.sort(key=lambda x: int(x.get("seqno") or 0))
    meta = {
        "group_by": group_by,
        "count_fn": count_fn,
        "append": appends,
        "pivot": pivot,
        "label_aliases": label_aliases,
    }
    return shown, sticky, groups_out, meta


def recalc_digest_rows(
    fields: list[dict[str, Any]],
    values: list[dict[str, Any]],
    totals: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Apply append.* formulas; mutate values; return updated totals."""
    recalc_fields = [
        f
        for f in fields
        if str((f.get("extra") or {}).get("aggrType") or "").lower() == "recalc"
        and formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None)
    ]
    if not recalc_fields:
        return totals

    totals_out = dict(totals or {})
    for f in fields:
        key = str(f.get("uukey") or "")
        ft = str(f.get("ftype") or "").upper()
        if ft in {"NUMERIC", "EXPENSE", "INTEGER", "FLOAT", "MONEY"} and key:
            if totals_out.get(key) in (None, ""):
                totals_out[key] = 0.0

    totals_objects = _flat_to_objects(fields, totals_out)

    def _recalc_one(row: dict[str, Any]) -> None:
        for f in fields:
            key = str(f.get("uukey") or "")
            ft = str(f.get("ftype") or "").upper()
            if ft in {"NUMERIC", "EXPENSE", "INTEGER", "FLOAT", "MONEY"} and key:
                if row.get(key) in (None, ""):
                    row[key] = 0.0
        objects = _flat_to_objects(fields, row)
        for f in recalc_fields:
            code = formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None)
            if not code:
                continue
            try:
                result = eval_append_formula(code, objects, totals_objects)
            except Exception:
                continue
            if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
                continue
            extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
            prec = extra.get("precision") if isinstance(extra, dict) else None
            if prec is not None and isinstance(result, (int, float)):
                try:
                    result = round(float(result), int(prec))
                except (TypeError, ValueError):
                    pass
            _write_formula_result(objects, f, result)
            key = str(f.get("uukey") or "")
            if key:
                row[key] = result

    for row in values:
        _recalc_one(row)
    if totals_out:
        _recalc_one(totals_out)
    return totals_out or None
