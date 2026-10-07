"""Project config/tables/inputs into TableSchema / InputSchema (worth FE shape)."""

from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx
from modoor.engine.registry import ModelBundle


def _field_key(raw: dict[str, Any], fallback: str) -> str:
    return str(raw.get("uukey") or raw.get("index") or fallback)


def normalize_field(key: str, raw: dict[str, Any], *, group_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    data = copy.deepcopy(raw)
    group = str(data.get("group") or (key.split(".", 1)[0] if "." in key else "basic"))
    field = str(data.get("field") or (key.split(".", 1)[-1] if "." in key else key))
    gmeta = group_meta or {}
    extra = dict(data.get("extra") or {})
    refer = data.get("refer")
    if not refer and str(data.get("ftype") or "").upper() == "RELATION":
        using = str(data.get("using") or extra.get("relation") or "")
        if using:
            refer = {
                "uukey": "",
                "keyby": str(extra.get("dataKey") or "basic.uukey"),
                "txtby": str(extra.get("textKey") or "basic.name"),
                "image": "",
                "using": using,
            }
            extra.setdefault("relation", using)
    out: dict[str, Any] = {
        "uukey": _field_key(data, key),
        "gtype": data.get("gtype") or gmeta.get("gtype") or "FLATTEN",
        "gname": data.get("gname") or gmeta.get("title") or group,
        "ftype": str(data.get("ftype") or "STRINGS"),
        "group": group,
        "field": field,
        "label": data.get("label") or field,
        "index": data.get("index") or key,
        "shown": True if data.get("shown") is None else bool(data.get("shown")),
        "extra": extra,
    }
    if data.get("remark"):
        out["remark"] = data["remark"]
    if data.get("seqno") is not None:
        out["seqno"] = data["seqno"]
    if data.get("width") is not None:
        out["width"] = data["width"]
    if data.get("using"):
        out["using"] = data["using"]
    if refer:
        out["refer"] = refer
    if extra.get("options"):
        out["options"] = extra["options"]
    return out


def _match_field_keys(pattern: str, all_keys: list[str]) -> list[str]:
    if pattern == ".*":
        return list(all_keys)
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return [k for k in all_keys if k.startswith(prefix)]
    if "*" in pattern or "?" in pattern:
        rx = re.compile("^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$")
        return [k for k in all_keys if rx.match(k)]
    return [pattern] if pattern in all_keys else []


def resolve_view_fields(
    bundle: ModelBundle,
    *,
    using: str,
    kind: str,
) -> tuple[dict[str, Any], list[str]]:
    """Return (view_def, ordered field keys). kind = table|input."""
    catalog = bundle.tables if kind == "table" else bundle.inputs
    view = catalog.get(using) or catalog.get("default") or {}
    view = dict(view)
    all_keys = sorted(
        bundle.fields.keys(),
        key=lambda k: int(bundle.fields[k].get("seqno") or 9999),
    )
    patterns = list(view.get("fields") or ([".*"] if kind == "table" else all_keys))
    if not patterns and kind == "input":
        groups = list(view.get("groups") or [])
        if groups:
            patterns = [k for k in all_keys if (bundle.fields[k].get("group") in groups)]
        else:
            patterns = [".*"]
    ordered: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for key in _match_field_keys(str(pat), all_keys):
            if key not in seen:
                ordered.append(key)
                seen.add(key)
    hidden_pats = list(view.get("hidden") or [])
    hidden: set[str] = set()
    for pat in hidden_pats:
        hidden.update(_match_field_keys(str(pat), all_keys))
    ordered = [k for k in ordered if k not in hidden]
    return view, ordered


def build_source(bundle: ModelBundle) -> dict[str, Any]:
    """schema.source：仅 fields / groups / clicks（不含 tables、inputs、model）。"""
    groups = {}
    for gk, g in bundle.groups.items():
        groups[gk] = copy.deepcopy(g)
        groups[gk].setdefault("uukey", gk)
        groups[gk].setdefault("model", bundle.uukey)
    fields = {
        key: normalize_field(key, raw, group_meta=groups.get(str(raw.get("group") or "")))
        for key, raw in bundle.fields.items()
    }
    return {
        "fields": fields,
        "groups": groups,
        "clicks": copy.deepcopy(bundle.clicks),
    }


def option_refers(fields: list[dict[str, Any]]) -> dict[str, Any]:
    refers: dict[str, Any] = {}
    for f in fields:
        extra = f.get("extra") or {}
        opts = f.get("options") or extra.get("options") or []
        if opts:
            refers[f["uukey"]] = [
                {
                    "uukey": o.get("uukey") or o.get("value"),
                    "label": o.get("label") or o.get("value"),
                    "value": o.get("value") or o.get("label"),
                    "short": o.get("short") or "",
                    "parent": o.get("parent") or "",
                }
                for o in opts
                if isinstance(o, dict)
            ]
        dict_key = extra.get("dictKey")
        if dict_key and opts:
            # also expose short dict key suffix for worth parity
            short = str(dict_key).split(":", 1)[-1]
            refers.setdefault(short, refers[f["uukey"]])
    return refers


def merge_dict_key_refers(
    session: Session,
    ctx: Ctx,
    fields: list[dict[str, Any]],
    refers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """用 base_cfg（模型 base_config）补全 OPTIONAL 的 dictKey。"""
    out = dict(refers or {})
    keys = {
        str((f.get("extra") or {}).get("dictKey") or "").strip()
        for f in fields
        if (f.get("extra") or {}).get("dictKey")
    }
    if not keys:
        return out
    try:
        from builtin.base import domain as base_domain
    except ImportError:
        return out
    cache: dict[str, list[dict[str, Any]]] = {}
    for full in keys:
        parsed = base_domain.parse_dict_key(full)
        if not parsed:
            continue
        mod, typ = parsed
        cache_key = f"{mod}:{typ}"
        if cache_key not in cache:
            cache[cache_key] = base_domain.list_dict_options(
                session, ctx, mod=mod, type=typ
            )
        opts = cache[cache_key]
        if not opts:
            continue
        out[typ] = opts
        out[full] = opts
        out[cache_key] = opts
    for f in fields:
        extra = f.get("extra") or {}
        dk = str(extra.get("dictKey") or "").strip()
        if not dk:
            continue
        parsed = base_domain.parse_dict_key(dk)
        if not parsed:
            continue
        mod, typ = parsed
        opts = cache.get(f"{mod}:{typ}") or []
        if opts and f.get("uukey"):
            out[f["uukey"]] = opts
    return out


def _normalize_toolbar_click(cid: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize click dict; map legacy INSERT/DELETE BUTTON onto record.create/delete."""
    item = copy.deepcopy(raw)
    item.setdefault("uukey", cid)
    ctype = str(item.get("ctype") or "").upper()
    action = str(item.get("action") or "").upper()
    uk = str(item.get("uukey") or cid)
    canonical_create = uk in ("record.create", "create", "INSERT") or action in ("INSERT", "CREATE")
    is_create = canonical_create or action == "RECORD.CREATE"
    if ctype == "BUTTON" and is_create:
        # Keep distinct menu items such as create.general; only the bare create id collapses.
        if canonical_create:
            item["uukey"] = "create"
        item["action"] = "record.create"
        item.setdefault("label", item.get("label") or "新增")
        item["ctype"] = "button"
    elif ctype == "BUTTON" and (
        action in ("DELETE", "RECORD.DELETE") or uk in ("record.delete", "delete", "DELETE")
    ):
        item["uukey"] = "delete"
        item["action"] = "record.delete"
        item.setdefault("label", item.get("label") or "删除")
        item["ctype"] = "button"
    elif ctype == "ACTION" and (
        action in ("MODIFY", "RECORD.MODIFY", "EDIT", "RECORD.EDIT")
        or uk in ("record.modify", "modify", "edit", "record.edit", "MODIFY")
    ):
        if str(item.get("uukey") or "").lower() in ("", "edit", "record.edit"):
            item["uukey"] = "modify"
        else:
            item.setdefault("uukey", "modify")
        item["action"] = "record.modify"
        item.setdefault("label", item.get("label") or "编辑")
        item["ctype"] = "action"
    elif ctype == "BUTTON":
        item["ctype"] = "button"
    elif ctype == "ACTION":
        item["ctype"] = "action"
    elif not ctype:
        # Default placement: toolbar
        item["ctype"] = "button"
    return item


def _expand_click_ids(bundle: ModelBundle, click_ids: list[Any]) -> list[dict[str, Any]]:
    """Resolve view click refs, including duolali wildcards like [ORDER][*]."""
    clicks: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_norm: set[str] = set()

    def add_key(key: str) -> None:
        if key in seen_keys:
            return
        raw = bundle.clicks.get(key)
        if not raw:
            return
        seen_keys.add(key)
        item = _normalize_toolbar_click(key, raw)
        norm = f"{item.get('uukey')}|{item.get('action')}"
        if norm in seen_norm:
            return
        seen_norm.add(norm)
        clicks.append(item)

    button_keys = [
        k
        for k, raw in bundle.clicks.items()
        if str((raw or {}).get("ctype") or "").upper() == "BUTTON"
    ]
    action_keys = [
        k
        for k, raw in bundle.clicks.items()
        if str((raw or {}).get("ctype") or "").upper() == "ACTION"
    ]

    for cid in click_ids:
        ref = str(cid or "").strip()
        if not ref:
            continue
        if "[*]" in ref or ref.endswith(".*"):
            keys = button_keys + action_keys
            if keys:
                for k in keys:
                    add_key(k)
            else:
                # Fallback when config only has record.* without ctype=BUTTON
                for k in ("create", "record.create", "delete", "record.delete", "modify", "edit", "record.modify"):
                    add_key(k)
            continue
        if ref in bundle.clicks:
            add_key(ref)
            continue
        bare = ref.split("]", 1)[-1] if ref.startswith("[") and "]" in ref else ref
        if bare in bundle.clicks:
            add_key(bare)
            continue
        upper = bare.upper()
        if upper in ("INSERT", "CREATE"):
            add_key("create")
            add_key("record.create")
        elif upper in ("DELETE",):
            add_key("delete")
            add_key("record.delete")
        else:
            add_key(bare)
    return clicks


def project_table(
    bundle: ModelBundle,
    *,
    using: str,
    scene: str,
    page: int = 1,
    size: int = 50,
    query: dict[str, Any] | None = None,
    order: dict[str, Any] | None = None,
) -> dict[str, Any]:
    view, keys = resolve_view_fields(bundle, using=using, kind="table")
    groups_meta = bundle.groups
    extra = dict(view.get("extra") or {})
    from modoor.engine.digest import is_digest_view, project_digest_table

    digest_meta: dict[str, Any] | None = None
    if is_digest_view(extra):
        fields, sticky, groups, digest_meta = project_digest_table(
            bundle, using=using, view=view, others=extra
        )
    else:
        fields = [
            normalize_field(
                k,
                bundle.fields[k],
                group_meta=groups_meta.get(str(bundle.fields[k].get("group") or "")),
            )
            for k in keys
            if k in bundle.fields
        ]
        # 视图 fields 是默认显示和顺序；模型里其余字段带上，默认隐藏，供列设置勾选
        for f in fields:
            f["shown"] = True
        shown_keys = {str(f.get("uukey") or "") for f in fields}
        rest_keys = sorted(
            (k for k in bundle.fields if k not in shown_keys),
            key=lambda k: int(bundle.fields[k].get("seqno") or 9999),
        )
        for k in rest_keys:
            extra_field = normalize_field(
                k,
                bundle.fields[k],
                group_meta=groups_meta.get(str(bundle.fields[k].get("group") or "")),
            )
            extra_field["shown"] = False
            fields.append(extra_field)
        sticky = list(view.get("sticky") or [])
        if not sticky and any(f["uukey"] == "basic.uukey" for f in fields):
            sticky = ["basic.uukey"]
        groups = [
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

    click_ids = list(view.get("clicks") or [])
    clicks = _expand_click_ids(bundle, click_ids)
    from modoor.engine.query import merge_search_query

    default_query = merge_search_query(view.get("query") or {}, query)
    default_order = order or {"field": "basic.uukey", "order": "desc"}
    sheet_raw = extra.get("sheet")
    sheet: list[str] = []
    if isinstance(sheet_raw, list):
        for item in sheet_raw:
            s = str(item or "").strip().lower()
            if s in ("update", "insert") and s not in sheet:
                sheet.append(s)

    filter_keys = [str(x).strip() for x in (view.get("filters") or []) if str(x).strip()]
    # origin：原始字段定义（digest 度量可能改写 ftype）；快捷/侧栏筛选按 key 映射到此
    origin: dict[str, Any] = {}
    for key in filter_keys:
        if key in origin or key not in bundle.fields:
            continue
        origin[key] = normalize_field(
            key,
            bundle.fields[key],
            group_meta=groups_meta.get(str(bundle.fields[key].get("group") or "")),
        )
    for f in fields:
        key = str(f.get("uukey") or "").strip()
        if not key or key in origin or key not in bundle.fields:
            continue
        origin[key] = normalize_field(
            key,
            bundle.fields[key],
            group_meta=groups_meta.get(str(bundle.fields[key].get("group") or "")),
        )

    others = dict(extra)
    if digest_meta:
        others["$digest"] = digest_meta

    apply_view_labels(fields, view)
    if origin:
        apply_view_labels(list(origin.values()), view)

    refers_fields = list(fields)
    if origin:
        shown_keys = {str(f.get("uukey") or "") for f in fields}
        refers_fields.extend(f for k, f in origin.items() if k not in shown_keys)

    return {
        "model": bundle.uukey,
        "using": using,
        "title": view.get("title") or bundle.model.get("title") or bundle.uukey,
        "sticky": sticky,
        "groups": groups,
        "fields": fields,
        "origin": origin,
        "clicks": clicks,
        "filters": filter_keys,
        "refers": option_refers(refers_fields),
        "others": others,
        "sheet": sheet,
        "request": {
            "model": bundle.uukey,
            "uukey": "",
            "scene": scene or "SEARCH",
            "logid": "",
            "page": page,
            "size": size,
            "using": using,
            "query": default_query,
            "order": default_order,
        },
    }


def apply_view_labels(fields: list[dict[str, Any]], view: dict[str, Any]) -> None:
    """inputs/tables ``labels`` overrides the config label for this view only.

    A ``|`` in the override is a form line break, not part of the field name.
    """
    labels = view.get("labels") or {}
    if not isinstance(labels, dict):
        return
    for field in fields:
        key = str(field.get("uukey") or "")
        label = labels.get(key)
        if isinstance(label, str) and label.strip():
            field["label"] = label


def project_input(
    bundle: ModelBundle,
    *,
    using: str,
    scene: str,
    uukey: str = "",
) -> dict[str, Any]:
    view, keys = resolve_view_fields(bundle, using=using, kind="input")
    groups_meta = bundle.groups
    explicit_groups = list(view.get("groups") or [])
    if explicit_groups:
        group_ids = explicit_groups
    else:
        # 未声明 groups 时，只返回实际投影字段涉及的分组（避免 audit 空壳）
        group_ids = []
        for k in keys:
            raw = bundle.fields.get(k) or {}
            gk = str(raw.get("group") or "")
            if gk and gk not in group_ids:
                group_ids.append(gk)
    fields = [
        normalize_field(k, bundle.fields[k], group_meta=groups_meta.get(str(bundle.fields[k].get("group") or "")))
        for k in keys
        if k in bundle.fields
    ]
    apply_view_labels(fields, view)
    groups = []
    for gk in group_ids:
        g = groups_meta.get(gk)
        if not g:
            continue
        item = copy.deepcopy(g)
        item.setdefault("uukey", gk)
        item.setdefault("model", bundle.uukey)
        groups.append(item)
    preset = dict(view.get("preset") or {})
    return {
        "title": view.get("title") or "表单",
        "groups": groups,
        "fields": fields,
        "values": dict(preset),
        "refers": option_refers(fields),
        "request": {
            "model": bundle.uukey,
            "uukey": uukey,
            "logid": "",
            "using": using,
            "scene": scene or ("DETAIL" if uukey else "INSERT"),
        },
    }
