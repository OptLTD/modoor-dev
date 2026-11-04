"""Field formula autofill (option-worth subset): depends DAG + safe AST eval."""

from __future__ import annotations

import ast
import math
import re
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
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
        "FLOOR",
        "floor",
        "CEIL",
        "ceil",
        "CEILING",
        "ceiling",
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


def normalize_formula(code: str) -> str:
    """压平换行/多空格，便于 ast.parse。"""
    return " ".join(str(code or "").split())


def formula_text(extra: dict[str, Any] | None) -> str:
    if not isinstance(extra, dict):
        return ""
    raw = extra.get("formula")
    if raw is None or raw is False:
        return ""
    if isinstance(raw, bool):
        return ""
    # 字段设置里公式常带换行，ast.parse 不接受；压成单行空格
    return normalize_formula(str(raw))


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
    """Keep field.extra.depends aligned with identifiers in formula.

    Formula is the source of truth: stale depends (e.g. after a low-table
    formula override that left config depends untouched) are replaced.
    """
    extra = dict(field.get("extra") or {})
    code = formula_text(extra)
    if not code:
        field["extra"] = extra
        return field
    extra["depends"] = parse_depends_from_formula(code)
    field["extra"] = extra
    return field


def find_formula_dependency_cycle(fields: list[dict[str, Any]]) -> list[str] | None:
    """若公式字段互相引用成环，返回一条环路径（首尾同节点）；否则 None。

    仅看「公式字段 → 公式字段」边；引用普通输入字段不算环。
    自引用（公式里写了自己）视为环。
    """
    work = [ensure_field_depends(dict(f)) for f in fields if isinstance(f, dict)]
    formula_keys = {
        _field_key(f)
        for f in work
        if _field_key(f)
        and formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None)
    }
    if not formula_keys:
        return None

    graph: dict[str, list[str]] = {}
    for f in work:
        key = _field_key(f)
        if key not in formula_keys:
            continue
        deps = _depends_of(f)
        if key in deps:
            return [key, key]
        graph[key] = [d for d in deps if d in formula_keys and d != key]

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        if node in visiting:
            idx = stack.index(node)
            return stack[idx:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for nxt in graph.get(node, []):
            hit = dfs(nxt)
            if hit:
                return hit
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for key in graph:
        hit = dfs(key)
        if hit:
            return hit
    return None


def assert_no_formula_cycles(fields: list[dict[str, Any]]) -> None:
    """公式字段存在循环依赖时抛 ValueError（供保存/计算上报用户）。"""
    cycle = find_formula_dependency_cycle(fields)
    if not cycle:
        return
    path = " → ".join(cycle)
    raise ValueError(f"公式字段存在循环依赖: {path}")


def ensure_fields_depends(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill missing depends from formula, then expand transitive formula deps (option-worth style).

    展开时遇环会截断（不抛错），便于 schema 仍能返回；环应在保存/计算时用
    ``assert_no_formula_cycles`` 拦截。
    """
    out = [ensure_field_depends(dict(f)) for f in fields]
    by_key = {_field_key(f): f for f in out if _field_key(f)}

    def expand(key: str, seen: set[str]) -> list[str]:
        if key in seen:
            return []
        seen.add(key)
        f = by_key.get(key)
        if not f:
            return []
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
    remaining = {_field_key(f): f for f in items if _field_key(f)}
    layers: list[list[dict[str, Any]]] = []
    while remaining:
        layer: list[dict[str, Any]] = []
        for k, f in list(remaining.items()):
            deps = [d for d in _depends_of(f) if d in key_set and d != k]
            if any(d in remaining for d in deps):
                continue
            layer.append(f)
        if not layer:
            stuck = sorted(remaining.keys())
            raise ValueError(
                "公式字段存在循环依赖: " + " → ".join(stuck[:8]) + ("…" if len(stuck) > 8 else "")
            )
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
        if key in ("FLOOR", "CEIL", "CEILING"):
            if not args:
                raise ValueError(f"{name} expects 1 or 2 args")
            try:
                value = Decimal(str(args[0] or 0))
            except (ArithmeticError, ValueError):
                value = Decimal(0)
            try:
                step = Decimal(str(args[1])) if len(args) > 1 else Decimal(1)
            except (ArithmeticError, ValueError):
                step = Decimal(1)
            if step == 0:
                return 0.0
            rounding = ROUND_FLOOR if key == "FLOOR" else ROUND_CEILING
            return float((value / step).to_integral_value(rounding=rounding) * step)
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
            # 与 Excel 一致：必须是 condition/value 成对；无匹配时请写 true, 默认值
            if len(args) < 2 or len(args) % 2 != 0:
                raise ValueError(
                    "IFS 需要成对的条件/值（与 Excel 一致）；无匹配默认请写 true, 默认值"
                )
            for i in range(0, len(args), 2):
                if _truthy(args[i]):
                    return args[i + 1]
            return 0
        raise ValueError(f"unsupported function: {name}")


def validate_formula(code: str) -> str:
    """校验公式可解析，且 IFS/IF 参数个数合法。返回规范化后的公式文本。

    失败抛 ValueError，供字段/公式设置保存或计算路径上报给用户。
    """
    text = normalize_formula(code)
    if not text:
        return ""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        tip = getattr(exc, "msg", None) or str(exc)
        raise ValueError(f"公式语法错误: {tip}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        key = name.upper()
        argc = len(node.args)
        if key == "IFS":
            if argc < 2 or argc % 2 != 0:
                raise ValueError(
                    "IFS 需要成对的条件/值（与 Excel 一致）；无匹配默认请写 true, 默认值"
                )
        elif key == "IF":
            if argc < 2 or argc > 3:
                raise ValueError("IF 需要 2 或 3 个参数：IF(条件, 真值, 假值?)")
    return text


def eval_formula(code: str, objects: dict[str, Any]) -> Any:
    text = normalize_formula(code)
    validate_formula(text)
    tree = ast.parse(text, mode="eval")
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


def stored_digits(extra: dict[str, Any] | None) -> int | None:
    """小数位：公式结果按 scale 落库；未写 scale 时沿用 precision。precision 仍是展示位数。"""
    if not isinstance(extra, dict):
        return None
    raw = extra.get("scale")
    if raw in (None, ""):
        raw = extra.get("precision")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def apply_formulas(fields: list[dict[str, Any]], flat: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all formula fields; return full flat map (input merged with formula outputs).

    公式非法或求值失败时抛错（不再静默跳过），便于用户回字段/公式设置修正。
    """
    from modoor.core.errors import AppError

    work_fields = [dict(f) for f in fields]
    try:
        assert_no_formula_cycles(work_fields)
    except ValueError as exc:
        raise AppError("formula_error", str(exc)) from exc

    items = _collect_formula_fields(work_fields)
    objects = _flat_to_objects(work_fields, dict(flat or {}))
    if not items:
        return dict(flat or {})

    dep_keys: set[str] = set()
    for it in items:
        dep_keys.update(_depends_of(it))
    _fill_numeric_defaults(work_fields, objects, dep_keys)

    try:
        layers = _layer_by_depends(items)
    except ValueError as exc:
        raise AppError("formula_error", str(exc)) from exc

    for layer in layers:
        for f in layer:
            code = formula_text(f.get("extra") if isinstance(f.get("extra"), dict) else None)
            if not code:
                continue
            key = _field_key(f) or str(f.get("field") or "formula")
            label = str(f.get("label") or key)
            try:
                result = eval_formula(code, objects)
            except Exception as exc:  # noqa: BLE001
                raise AppError(
                    "formula_error",
                    f"字段「{label}」({key}) 公式计算失败: {exc}",
                    {"field": key, "formula": code},
                ) from exc
            if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
                raise AppError(
                    "formula_error",
                    f"字段「{label}」({key}) 公式结果无效 (NaN/Inf)",
                    {"field": key, "formula": code},
                )
            extra = f.get("extra") if isinstance(f.get("extra"), dict) else {}
            prec = stored_digits(extra)
            if prec is not None and isinstance(result, (int, float)) and not isinstance(result, bool):
                result = round(float(result), prec)
            _write_formula_result(objects, f, result)

    patch = _objects_to_flat_patch(items, objects)
    out = dict(flat or {})
    out.update(patch)
    return out
