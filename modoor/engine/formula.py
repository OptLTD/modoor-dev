"""Field formula autofill (option-worth subset): depends DAG + safe AST eval."""

from __future__ import annotations

import ast
import math
import re
from datetime import datetime
from typing import Any

_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b")
_ALLOWED_FUNCS = frozenset(
    {
        "HOURS",
        "hours",
        "ABS",
        "abs",
        "ROUND",
        "round",
        "MIN",
        "min",
        "MAX",
        "max",
        "IF",
        "if",
        "IFS",
        "ifs",
    }
)


def formula_text(extra: dict[str, Any] | None) -> str:
    if not isinstance(extra, dict):
        return ""
    raw = extra.get("formula")
    if raw is None or raw is False:
        return ""
    if isinstance(raw, bool):
        return ""
    return str(raw).strip()


def parse_depends_from_formula(code: str) -> list[str]:
    if not code:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _IDENT_RE.finditer(code):
        key = m.group(1)
        if key in seen:
            continue
        # skip function names used as bare idents (HOURS is Call, not Attribute path)
        if "." not in key:
            continue
        seen.add(key)
        out.append(key)
    return out


def ensure_field_depends(field: dict[str, Any]) -> dict[str, Any]:
    """Mutate field.extra.depends when formula exists but depends missing."""
    extra = dict(field.get("extra") or {})
    code = formula_text(extra)
    if not code:
        field["extra"] = extra
        return field
    deps = extra.get("depends")
    if isinstance(deps, list) and any(str(d).strip() for d in deps):
        field["extra"] = extra
        return field
    extra["depends"] = parse_depends_from_formula(code)
    field["extra"] = extra
    return field


def ensure_fields_depends(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill missing depends from formula, then expand transitive formula deps (option-worth style)."""
    out = [ensure_field_depends(dict(f)) for f in fields]
    by_key = {_field_key(f): f for f in out if _field_key(f)}

    def expand(key: str, seen: set[str]) -> list[str]:
        if key in seen:
            return []
        seen.add(key)
        f = by_key.get(key)
        if not f:
            return []
        extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
        deps = list(_depends_of(f))
        acc: list[str] = []
        for d in deps:
            if d not in acc:
                acc.append(d)
            # if dependency is itself a formula field, include its depends
            if d in by_key and formula_text(
                by_key[d].get("extra") if isinstance(by_key[d].get("extra"), dict) else None
            ):
                for up in expand(d, seen):
                    if up not in acc:
                        acc.append(up)
        return acc

    for f in out:
        if not formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None):
            continue
        key = _field_key(f)
        expanded = expand(key, set())
        # remove self
        expanded = [d for d in expanded if d != key]
        extra = dict(f.get("extra") or {})
        extra["depends"] = expanded
        f["extra"] = extra
    return out


def _field_key(f: dict[str, Any]) -> str:
    return str(f.get("uukey") or f.get("index") or "").strip()


def _collect_formula_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in fields:
        ensure_field_depends(f)
        if formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None):
            out.append(f)
    return out


def _depends_of(f: dict[str, Any]) -> list[str]:
    extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
    deps = extra.get("depends") if isinstance(extra, dict) else None
    if not isinstance(deps, list):
        return []
    return [str(d).strip() for d in deps if str(d).strip()]


def _layer_by_depends(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    key_set = {_field_key(f) for f in items}
    remaining = { _field_key(f): f for f in items if _field_key(f) }
    layers: list[list[dict[str, Any]]] = []
    while remaining:
        layer: list[dict[str, Any]] = []
        for k, f in list(remaining.items()):
            deps = [d for d in _depends_of(f) if d in key_set and d != k]
            if any(d in remaining for d in deps):
                continue
            layer.append(f)
        if not layer:
            # cycle / unresolved — dump rest in schema order
            layer = list(remaining.values())
            layers.append(layer)
            break
        for f in layer:
            remaining.pop(_field_key(f), None)
        layers.append(layer)
    return layers


def _ensure_group(objects: dict[str, Any], group: str) -> dict[str, Any]:
    cur = objects.get(group)
    if isinstance(cur, dict):
        return cur
    nested: dict[str, Any] = {}
    objects[group] = nested
    return nested


def _set_path(objects: dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    if len(parts) == 1:
        objects[parts[0]] = value
        return
    cur: dict[str, Any] = objects
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _flat_to_objects(fields: list[dict[str, Any]], flat: dict[str, Any]) -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for f in fields:
        key = _field_key(f)
        group = str(f.get("group") or "")
        field = str(f.get("field") or "")
        val = None
        if key and key in flat:
            val = flat[key]
        elif field and field in flat:
            val = flat[field]
        else:
            continue
        if group:
            _ensure_group(objects, group)[field] = val
            if key and "." in key:
                _set_path(objects, key, val)
        else:
            objects[field] = val
            if key:
                objects[key] = val
    # also merge any leftover flat dotted keys
    for k, v in flat.items():
        if isinstance(k, str) and "." in k:
            _set_path(objects, k, v)
    return objects


def _objects_to_flat_patch(fields: list[dict[str, Any]], objects: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields:
        key = _field_key(f)
        if not key:
            continue
        group = str(f.get("group") or "")
        field = str(f.get("field") or "")
        val = None
        if group and isinstance(objects.get(group), dict):
            val = objects[group].get(field)
        elif field in objects:
            val = objects.get(field)
        if val is None and key in objects:
            val = objects.get(key)
        if val is None:
            # walk dotted path
            parts = key.split(".")
            cur: Any = objects
            for p in parts:
                if not isinstance(cur, dict) or p not in cur:
                    cur = None
                    break
                cur = cur[p]
            val = cur
        if val is not None:
            out[key] = val
    return out


def _is_numeric_ftype(ftype: str) -> bool:
    return str(ftype or "").upper() in {"NUMERIC", "EXPENSE", "INTEGER", "FLOAT", "MONEY"}


def _fill_numeric_defaults(
    fields: list[dict[str, Any]],
    objects: dict[str, Any],
    dep_keys: set[str],
) -> None:
    by_key = {_field_key(f): f for f in fields if _field_key(f)}
    formula_keys = {
        _field_key(f)
        for f in fields
        if formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None)
    }
    for dk in dep_keys:
        f = by_key.get(dk)
        if not f or dk in formula_keys:
            continue
        if not _is_numeric_ftype(str(f.get("ftype") or "")):
            continue
        group = str(f.get("group") or "")
        field = str(f.get("field") or "")
        if group:
            g = _ensure_group(objects, group)
            if field not in g or g[field] is None or g[field] == "":
                g[field] = 0.0
        else:
            if field not in objects or objects[field] is None or objects[field] == "":
                objects[field] = 0.0


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19] if " " in s or "T" in s else s[:10], fmt)
        except ValueError:
            continue
    return None


def _hours_diff(a: Any, b: Any) -> float:
    """HOURS(a-b) style: if given a single number, return it; if two datetimes via subtraction result..."""
    # Our AST rewrites HOURS(x-y) as call with BinOp evaluated first → number of seconds? 
    # Better: HOURS receives already-evaluated difference only if both are numbers.
    # For datetime, we handle HOURS with two args: HOURS(end, start) OR parse BinOp specially.
    if isinstance(a, (int, float)) and b is None:
        return float(a)
    da = _parse_dt(a)
    db = _parse_dt(b) if b is not None else None
    if da is not None and db is not None:
        return max(0.0, (da - db).total_seconds() / 3600.0)
    if da is not None and b is None:
        return 0.0
    try:
        return float(a or 0)
    except (TypeError, ValueError):
        return 0.0


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return False
    if isinstance(v, (int, float)):
        return float(v) != 0.0
    return bool(v)


def _eq(left: Any, right: Any) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return str(left if left is not None else "") == str(right if right is not None else "")
    try:
        return float(left or 0) == float(right or 0)
    except (TypeError, ValueError):
        return left == right


class _SafeEval(ast.NodeVisitor):
    def __init__(self, env: dict[str, Any]):
        self.env = env

    def visit(self, node: ast.AST) -> Any:  # type: ignore[override]
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor is None:
            raise ValueError(f"unsupported expression: {node.__class__.__name__}")
        return visitor(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float, str, bool)) or node.value is None:
            return node.value
        raise ValueError("unsupported constant")

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in ("true", "True", "TRUE"):
            return True
        if node.id in ("false", "False", "FALSE"):
            return False
        if node.id in self.env:
            return self.env[node.id]
        raise ValueError(f"unknown name: {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        base = self.visit(node.value)
        if isinstance(base, dict):
            if node.attr in base:
                return base[node.attr]
            return 0
        raise ValueError("attribute on non-object")

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            if isinstance(op, ast.Eq):
                ok = _eq(left, right)
            elif isinstance(op, ast.NotEq):
                ok = not _eq(left, right)
            elif isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                try:
                    lv = float(left or 0)
                    rv = float(right or 0)
                except (TypeError, ValueError) as exc:
                    raise ValueError("non-numeric comparison") from exc
                if isinstance(op, ast.Lt):
                    ok = lv < rv
                elif isinstance(op, ast.LtE):
                    ok = lv <= rv
                elif isinstance(op, ast.Gt):
                    ok = lv > rv
                else:
                    ok = lv >= rv
            else:
                raise ValueError("unsupported comparison")
            if not ok:
                return False
            left = right
        return True

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        v = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +float(v or 0)
        if isinstance(node.op, ast.USub):
            return -float(v or 0)
        if isinstance(node.op, ast.Not):
            return not _truthy(v)
        raise ValueError("unsupported unary op")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        # datetime HOURS pattern: leave as numeric ops; HOURS() wraps result
        left = self.visit(node.left)
        right = self.visit(node.right)
        # if both datetime-like, subtraction → hours via float seconds handled in HOURS only;
        # for bare datetime minus, convert to hours so nested HOURS(a-b) works when rewritten.
        dl = _parse_dt(left)
        dr = _parse_dt(right)
        if dl is not None and dr is not None and isinstance(node.op, ast.Sub):
            return (dl - dr).total_seconds() / 3600.0
        try:
            lv = float(left or 0)
            rv = float(right or 0)
        except (TypeError, ValueError):
            raise ValueError("non-numeric binary op") from None
        if isinstance(node.op, ast.Add):
            return lv + rv
        if isinstance(node.op, ast.Sub):
            return lv - rv
        if isinstance(node.op, ast.Mult):
            return lv * rv
        if isinstance(node.op, ast.Div):
            if rv == 0:
                return 0.0
            return lv / rv
        if isinstance(node.op, ast.Mod):
            if rv == 0:
                return 0.0
            return lv % rv
        if isinstance(node.op, ast.Pow):
            return lv ** rv
        raise ValueError("unsupported binary op")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("unsupported call")
        name = node.func.id
        if name not in _ALLOWED_FUNCS:
            raise ValueError(f"unsupported function: {name}")
        args = [self.visit(a) for a in node.args]
        key = name.upper()
        if key == "HOURS":
            if len(args) == 1:
                # already hours if BinOp of datetimes, or numeric
                try:
                    return float(args[0] or 0)
                except (TypeError, ValueError):
                    return _hours_diff(args[0], None)
            if len(args) == 2:
                return _hours_diff(args[0], args[1])
            raise ValueError("HOURS expects 1 or 2 args")
        if key == "ABS":
            return abs(float(args[0] or 0))
        if key == "ROUND":
            nd = int(args[1]) if len(args) > 1 else 0
            return round(float(args[0] or 0), nd)
        if key == "MIN":
            return min(float(a or 0) for a in args)
        if key == "MAX":
            return max(float(a or 0) for a in args)
        if key == "IF":
            if len(args) < 2:
                raise ValueError("IF expects 2 or 3 args")
            if _truthy(args[0]):
                return args[1]
            return args[2] if len(args) > 2 else 0
        if key == "IFS":
            if len(args) < 2 or len(args) % 2 != 0:
                raise ValueError("IFS expects condition/value pairs")
            for i in range(0, len(args), 2):
                if _truthy(args[i]):
                    return args[i + 1]
            return 0
        raise ValueError(f"unsupported function: {name}")


def eval_formula(code: str, objects: dict[str, Any]) -> Any:
    tree = ast.parse(code, mode="eval")
    return _SafeEval(objects).visit(tree)


def _write_formula_result(objects: dict[str, Any], field: dict[str, Any], value: Any) -> None:
    key = _field_key(field)
    group = str(field.get("group") or "")
    name = str(field.get("field") or "")
    if group:
        _ensure_group(objects, group)[name] = value
    else:
        objects[name] = value
    if key:
        _set_path(objects, key, value)


def apply_formulas(fields: list[dict[str, Any]], flat: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all formula fields; return full flat map (input merged with formula outputs)."""
    work_fields = [dict(f) for f in fields]
    items = _collect_formula_fields(work_fields)
    objects = _flat_to_objects(work_fields, dict(flat or {}))
    if not items:
        return dict(flat or {})

    dep_keys: set[str] = set()
    for it in items:
        dep_keys.update(_depends_of(it))
    _fill_numeric_defaults(work_fields, objects, dep_keys)

    for layer in _layer_by_depends(items):
        for f in layer:
            code = formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None)
            if not code:
                continue
            try:
                result = eval_formula(code, objects)
            except Exception:
                continue
            if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
                continue
            # precision
            extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
            prec = extra.get("precision") if isinstance(extra, dict) else None
            if prec is not None and isinstance(result, (int, float)):
                try:
                    result = round(float(result), int(prec))
                except (TypeError, ValueError):
                    pass
            _write_formula_result(objects, f, result)

    patch = _objects_to_flat_patch(items, objects)
    out = dict(flat or {})
    out.update(patch)
    return out
