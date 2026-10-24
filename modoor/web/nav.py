"""Load PC shell menus from module manifests + live external registry."""


from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from modoor.core.settings import get_settings
from modoor.platform.module_state import discover_manifests
from modoor.platform.services import get_by_module, get_entry_url, list_services
from modoor.platform.manifest_i18n import APP_LABEL_KEY, normalize_manifest_i18n
from modoor.support import seqno, text, texts

# re-export for callers / tests
__all__ = ["APP_LABEL_KEY"]


def _menu_path(raw: dict[str, Any]) -> str:
    return text(raw.get("path") or raw.get("route"), strip=True)


def _normalize_menu(raw: dict[str, Any], *, mid: str, fallback_id: str) -> dict[str, Any] | None:
    """Leaf needs path; group needs items. Nested ``items`` (alias ``children``) supported."""
    items_raw = list(raw.get("items") or raw.get("children") or [])
    items_raw.sort(key=lambda m: (seqno(m.get("seqno"), 100), text(m.get("label"))))
    items: list[dict[str, Any]] = []
    for j, child in enumerate(items_raw):
        normalized = _normalize_menu(
            child if isinstance(child, dict) else {},
            mid=mid,
            fallback_id=f"{fallback_id}.{j}",
        )
        if normalized:
            items.append(normalized)

    path = _menu_path(raw)
    menu_id = text(raw.get("id")) or fallback_id
    if not path and not items:
        return None
    item: dict[str, Any] = {
        "id": menu_id,
        "label": raw.get("label") or menu_id or "Menu",
        "seqno": seqno(raw.get("seqno"), 100),
    }
    if path:
        item["path"] = path
    access = texts(raw.get("access"))
    if access:
        item["access"] = access
    industry = _menu_industry(raw.get("industry"))
    if industry:
        item["industry"] = industry
    if items:
        item["items"] = items
    return item


def _normalize_replace(raw: Any, *, mid: str) -> dict[str, Any]:
    """Host menu overrides from module.yaml ``replace``.

    A null or false value removes that menu id. A mapping patches only the
    fields it sets (``path``, ``label``, ``seqno``, ``access``, ``industry``,
    ``items``).
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        menu_id = text(key, strip=True)
        if not menu_id:
            continue
        if value is None or value is False:
            out[menu_id] = None
            continue
        if not isinstance(value, dict):
            continue
        patch: dict[str, Any] = {}
        if "path" in value or "route" in value:
            patch["path"] = _menu_path(value)
        if "label" in value and value.get("label") is not None:
            patch["label"] = text(value.get("label"))
        if "seqno" in value:
            patch["seqno"] = seqno(value.get("seqno"), 100)
        if "access" in value:
            patch["access"] = texts(value.get("access"))
        if "industry" in value:
            patch["industry"] = _menu_industry(value.get("industry"))
        if "items" in value:
            items: list[dict[str, Any]] = []
            for j, child in enumerate(value.get("items") or []):
                if not isinstance(child, dict):
                    continue
                normalized = _normalize_menu(child, mid=mid, fallback_id=f"{menu_id}.{j}")
                if normalized:
                    items.append(normalized)
            patch["items"] = items
        out[menu_id] = patch
    return out


def filter_menus_by_industry(menus: list[dict[str, Any]], industry: str) -> list[dict[str, Any]]:
    """Drop menus tagged for another industry. ``all`` and untagged menus stay.

    A group with no path is dropped once every child is gone.
    """
    current = text(industry or "all", strip=True).lower()
    if not current or current == "all":
        return menus
    out: list[dict[str, Any]] = []
    for menu in menus:
        declared = [item.lower() for item in texts(menu.get("industry"))]
        if declared and current not in declared:
            continue
        item = dict(menu)
        if menu.get("items"):
            nested = filter_menus_by_industry(list(menu.get("items") or []), current)
            if not menu.get("path") and not nested:
                continue
            if nested:
                item["items"] = nested
            else:
                item.pop("items", None)
        out.append(item)
    return out


def _menu_seq(menu: dict[str, Any]) -> int:
    return seqno(menu.get("seqno"), 100)


def _by_seq_label(menu: dict[str, Any]) -> tuple[int, str]:
    return (_menu_seq(menu), text(menu.get("label")))


def apply_menu_replace(
    menus: list[dict[str, Any]],
    replace: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Apply ``replace`` onto a menu tree. ``None`` drops that id."""
    if not replace:
        return list(menus)
    out: list[dict[str, Any]] = []
    for menu in menus:
        menu_id = text(menu.get("id"))
        has = menu_id in replace
        spec = replace.get(menu_id) if has else None
        if has and spec is None:
            continue
        item = dict(menu)
        if isinstance(spec, dict):
            if spec.get("path"):
                item["path"] = spec["path"]
            if "label" in spec and spec.get("label") is not None:
                item["label"] = spec["label"]
            if "seqno" in spec and spec.get("seqno") is not None:
                item["seqno"] = spec["seqno"]
            if spec.get("access"):
                item["access"] = spec["access"]
            if spec.get("industry"):
                item["industry"] = spec["industry"]
            if "items" in spec:
                if spec.get("items"):
                    item["items"] = list(spec["items"])
                else:
                    item.pop("items", None)
        if item.get("items"):
            nested = apply_menu_replace(list(item["items"]), replace)
            if nested:
                item["items"] = nested
            else:
                item.pop("items", None)
        if not item.get("path") and not item.get("items"):
            continue
        out.append(item)
    return out


def _copy_i18n(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for loc, pack in raw.items():
        out[str(loc)] = dict(pack) if isinstance(pack, dict) else {}
    return out


def merge_blended_menus(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Graft modules with ``blend`` onto the host menu. Both shells share that tree."""
    by_id = {text(mod.get("id")): mod for mod in modules}
    guests = [mod for mod in modules if text(mod.get("blend")) in by_id]
    if not guests:
        return modules
    grouped: dict[str, list[dict[str, Any]]] = {}
    for guest in guests:
        grouped.setdefault(text(guest.get("blend")), []).append(guest)
    merged: dict[str, dict[str, Any]] = {}
    for host_id, host_guests in grouped.items():
        host = by_id.get(host_id)
        if not host:
            continue
        replace: dict[str, Any] = {}
        for guest in host_guests:
            guest_replace = guest.get("replace") or {}
            if isinstance(guest_replace, dict):
                replace.update(guest_replace)
        menus = apply_menu_replace(list(host.get("menus") or []), replace)
        for guest in host_guests:
            menus.extend(list(guest.get("menus") or []))
        menus.sort(key=_by_seq_label)
        i18n = _copy_i18n(host.get("i18n"))
        for guest in host_guests:
            extra = guest.get("i18n")
            _merge_i18n(i18n, extra if isinstance(extra, dict) else None)
        merged[host_id] = {"menus": menus, "i18n": i18n}
    out: list[dict[str, Any]] = []
    for mod in modules:
        host_id = text(mod.get("blend"))
        chosen = host_id if host_id in merged else text(mod.get("id"))
        hit = merged.get(chosen)
        if not hit:
            out.append(mod)
            continue
        item = dict(mod)
        item["menus"] = hit["menus"]
        item["i18n"] = hit["i18n"]
        out.append(item)
    return out


def mark_blend_listing(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide a module that another module blends. The shell identity stays with the blender."""
    owners: dict[str, str] = {}
    for mod in modules:
        target = text(mod.get("blend"), strip=True)
        owner = text(mod.get("id"), strip=True)
        if target and owner and target not in owners:
            owners[target] = owner
    out: list[dict[str, Any]] = []
    for mod in modules:
        item = dict(mod)
        item.pop("blend", None)
        owner = owners.get(text(item.get("id")))
        if owner:
            item["listed"] = False
            item["shell"] = owner
        else:
            item["listed"] = True
        out.append(item)
    return out


def _tenant_menu_industry(session: Any, tenant_id: int) -> str:
    """Current tenant industry. Fleet stores it; other installs show every menu."""
    try:
        from module.fleet.domain.industry import active_industry
    except ImportError:
        return "all"
    from modoor.core.ctx import Ctx

    return active_industry(session, Ctx(tenant=int(tenant_id), user_id=0, team_id=0))


def _mount_replace(replace: dict[str, Any], map_path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for menu_id, patch in replace.items():
        if patch is None:
            out[menu_id] = None
            continue
        item = dict(patch)
        if item.get("path"):
            item["path"] = map_path(item["path"])
        if item.get("items"):
            item["items"] = _map_menu_paths(list(item["items"]), map_path)
        out[menu_id] = item
    return out


def _menu_industry(raw: Any) -> list[str]:
    return texts(raw, unique=True)


def _first_leaf_path(menus: list[dict[str, Any]]) -> str:
    for m in menus:
        path = text(m.get("path"), strip=True)
        if path:
            return path
        nested = _first_leaf_path(list(m.get("items") or []))
        if nested:
            return nested
    return ""


def _map_menu_paths(
    menus: list[dict[str, Any]],
    map_path,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in menus:
        item = {**m}
        if item.get("path"):
            item["path"] = map_path(item["path"])
        kids = list(item.get("items") or [])
        if kids:
            item["items"] = _map_menu_paths(kids, map_path)
        if item.get("path") or item.get("items"):
            out.append(item)
    return out


def _merge_i18n(host: dict[str, Any], extra: dict[str, Any] | None) -> None:
    if not extra or not isinstance(extra, dict):
        return
    for loc, pack in extra.items():
        if not isinstance(pack, dict):
            continue
        bucket = host.setdefault(str(loc), {})
        if isinstance(bucket, dict):
            bucket.update({str(k): str(v) for k, v in pack.items()})


def _find_menu(menus: list[dict[str, Any]], menu_id: str) -> dict[str, Any] | None:
    for m in menus:
        if text(m.get("id")) == menu_id:
            return m
        hit = _find_menu(list(m.get("items") or []), menu_id)
        if hit:
            return hit
    return None


def _attach_extension_menus(
    host_menus: list[dict[str, Any]],
    contrib: list[dict[str, Any]],
    *,
    parent: str | None = None,
) -> None:
    """Merge extension menus into host list (optional parent group id)."""
    if not contrib:
        return
    if parent:
        group = _find_menu(host_menus, parent)
        if group is not None:
            kids = list(group.get("items") or [])
            kids.extend(contrib)
            kids.sort(key=_by_seq_label)
            group["items"] = kids
            return
    host_menus.extend(contrib)
    host_menus.sort(key=_by_seq_label)


def _load_ui_catalog() -> dict[str, dict[str, Any]]:
    """In-repo modules only (modules/*/module.yaml). External apps come from registry."""
    catalog: dict[str, dict[str, Any]] = {}
    pending_ext: list[tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
    for meta in discover_manifests(get_settings()):
        mid = meta["id"]
        path = Path(meta["path"]) / "module.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        ui = data.get("ui-web") or {}
        exports = data.get("exports") or {}
        top_i18n = meta.get("i18n") or normalize_manifest_i18n(data.get("i18n"))
        kind = text(ui.get("kind"), strip=True) or "app"
        # External apps must register at runtime — do not load from modules/
        if kind == "external":
            continue
        menus_raw = list(exports.get("menus") or [])
        menus_raw.sort(key=_by_seq_label)
        menus: list[dict[str, Any]] = []
        for i, m in enumerate(menus_raw):
            if not isinstance(m, dict):
                continue
            item = _normalize_menu(m, mid=mid, fallback_id=f"{mid}.{i}")
            if item:
                menus.append(item)
        home = ui.get("entry") or _first_leaf_path(menus) or f"/{mid}"
        # SPA-relative path (no host); external keeps absolute entry URL
        home_path = home if not str(home).startswith("http") else ""
        prefix = ui.get("base") or f"/{mid}"
        order = seqno(ui.get("seqno"), 1000)

        # Extension packages contribute menus/i18n into host; not a switcher app.
        if kind == "extension":
            host = text(ui.get("host"), strip=True)
            parent = text(ui.get("parent"), strip=True) or None
            if host:
                pending_ext.append((host, {"parent": parent}, menus, top_i18n if isinstance(top_i18n, dict) else {}))
            continue

        pkg = text(meta.get("pkg"))
        if pkg == "inbuilt":
            origin = "inbuilt"
        elif pkg == "lightapp":
            origin = "lightapp"
        else:
            origin = "module"
        blend = text(ui.get("blend"), strip=True)
        catalog[mid] = {
            "id": mid,
            "label": ui.get("label") or mid.title(),
            "i18n": top_i18n,
            "kind": kind,
            "blend": blend,
            "replace": _normalize_replace(data.get("replace"), mid=mid),
            "seqno": order,
            "home": home,
            "home_path": home_path,
            "entry": home,
            "base": prefix,
            "recommends": list(ui.get("recommends") or []),
            "source": "module",
            "origin": origin,
            "menus": menus,
        }

    for host_id, opts, menus, i18n in pending_ext:
        host = catalog.get(host_id)
        if not host:
            continue
        _attach_extension_menus(
            host.setdefault("menus", []),
            menus,
            parent=opts.get("parent"),
        )
        host_i18n = host.get("i18n")
        if not isinstance(host_i18n, dict):
            host_i18n = {}
            host["i18n"] = host_i18n
        _merge_i18n(host_i18n, i18n)

    return catalog


def clear_ui_cache() -> None:
    get_ui_catalog.cache_clear()


@lru_cache
def get_ui_catalog() -> dict[str, dict[str, Any]]:
    return _load_ui_catalog()


def modoor_base_url() -> str:
    settings = get_settings()
    return f"http://{settings.modoor_web_host}:{settings.modoor_web_port}"


def _href_on_gate(path: str) -> str:
    """Prefix a public MODOOR_MODULE_GATE. Intranet or empty stays a path."""
    from modoor.core.settings import public_module_gate

    raw = str(path or "")
    base = public_module_gate(get_settings().modoor_webui_url)
    if not base or raw.startswith(("http://", "https://")):
        return raw
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return f"{base}{raw}"


def meta_from_service(rec: Any) -> dict[str, Any]:
    mfest = rec.manifest or {}
    ui = mfest.get("ui-web") or {}
    top_i18n = normalize_manifest_i18n(mfest.get("i18n"))
    return {
        "id": rec.module_id,
        "label": rec.app_name or ui.get("label") or rec.module_id,
        "i18n": top_i18n,
        "kind": "external",
        "entry": rec.entry_url,
        "home": rec.entry_url,
        "base": "",
        "recommends": list(ui.get("recommends") or ["module_switcher", "logout"]),
        "source": "external",
        "menus": [],
        "exports": rec.exports,
        "service_id": rec.service_id,
    }


def get_module_meta(module_id: str) -> dict[str, Any]:
    """Resolve in-repo catalog first, then persisted / live external registry."""
    cat = get_ui_catalog().get(module_id)
    if cat:
        return cat
    rec = get_by_module(module_id)
    if rec:
        return meta_from_service(rec)
    return {}


def resolve_home(module_id: str, meta: dict[str, Any] | None = None) -> str:
    meta = meta or get_module_meta(module_id)
    if meta.get("kind") == "external" or meta.get("source") == "external":
        live = get_entry_url(module_id)
        if live:
            return live

    from modoor.web.entry import call_resolve_entry, entry_launch_href

    resolved = call_resolve_entry(module_id)
    if resolved is not None:
        href = entry_launch_href(resolved, shell_base=modoor_base_url())
        if href:
            return href

    return meta.get("home") or meta.get("entry") or f"/{module_id}"


def module_home(module_id: str) -> str:
    return resolve_home(module_id)


def module_menus(module_id: str) -> list[dict[str, str]]:
    return list(get_module_meta(module_id).get("menus") or [])


def detect_module(path: str) -> str | None:
    from modoor.web.mount import strip_web_mount

    catalog = get_ui_catalog()
    local = strip_web_mount(path)
    best: str | None = None
    best_len = -1
    for mid, meta in catalog.items():
        prefix = meta.get("base") or f"/{mid}"
        if not prefix:
            continue
        if local == prefix or local.startswith(prefix + "/"):
            if len(prefix) > best_len:
                best = mid
                best_len = len(prefix)
    return best


def profile_dict(user: Any | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "realname": user.realname,
        "email": user.email,
        "team_id": user.team_id,
        "tenant": user.tenant,
        "current": user.current,
    }


def switcher_items(
    enabled: set[str],
    *,
    allowed_modules: set[str] | None = None,
) -> list[dict[str, Any]]:
    """In-repo enabled modules + registered external apps (online or offline).

    When ``allowed_modules`` is set, only those module ids are returned (ability filter).
    ``None`` means unrestricted / no ability filter. Disabled externals are omitted.
    """
    from modoor.web.mount import join_web_mount

    catalog = get_ui_catalog()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    order = sorted(
        catalog.keys(),
        key=lambda mid: (seqno(catalog[mid].get("seqno"), 1000), mid),
    )
    for mid in order:
        if mid not in catalog:
            continue
        if mid not in enabled:
            continue
        if allowed_modules is not None and mid not in allowed_modules:
            continue
        meta = catalog[mid]
        if not meta.get("menus") and not meta.get("home") and not meta.get("entry"):
            continue
        home = resolve_home(mid, meta)
        local_home = meta.get("home_path") or meta.get("base") or f"/{mid}"
        if str(home).startswith("http"):
            from urllib.parse import urlparse

            parsed = urlparse(home)
            path = parsed.path or join_web_mount(local_home)
            href = home
        else:
            path = join_web_mount(str(home) or local_home)
            href = _href_on_gate(path)
        menus = _map_menu_paths(
            list(meta.get("menus") or []),
            lambda p: join_web_mount(p),
        )
        items.append(
            {
                "id": mid, "label": meta["label"],
                "i18n": meta.get("i18n") or {},
                "path": path, "href": href,
                "kind": meta.get("kind") or "app",
                "blend": text(meta.get("blend")),
                "replace": _mount_replace(dict(meta.get("replace") or {}), lambda p: join_web_mount(p)),
                "seqno": seqno(meta.get("seqno"), 1000),
                "entry": href, "menus": menus,
                "exports": None, "online": True,
                "exports_count": None,
                "source": "module",
                "origin": meta.get("origin") or "module",
            }
        )
        seen.add(mid)

    for svc in list_services():
        mid = svc.get("module_id") or svc.get("service_id")
        if not mid or mid in seen:
            continue
        if mid not in enabled:
            continue
        if allowed_modules is not None and mid not in allowed_modules:
            continue
        href = _href_on_gate(f"/go/{mid}")
        exports = (svc.get("manifest") or {}).get("exports") or {}
        arts = svc.get("artifacts") or {}
        mfest = svc.get("manifest") or {}
        ui = mfest.get("ui-web") or {}
        if not isinstance(ui, dict):
            ui = {}
        order = seqno(ui.get("seqno"), 2000)
        items.append(
            {
                "id": mid,
                "label": svc.get("app_name") or ui.get("label") or mid,
                "i18n": normalize_manifest_i18n(mfest.get("i18n")),
                "path": f"/go/{mid}",
                "href": href,
                "kind": "external",
                "seqno": order,
                "online": bool(svc.get("online", True)),
                "entry": svc.get("entry_url"),
                "exports": exports,
                "exports_count": {
                    "tools": len(exports.get("tools") or []),
                    "skills": len(exports.get("skills") or []),
                    "models": len(arts.get("models") or []),
                },
                "source": "external",
                "origin": "module",
            }
        )
        seen.add(mid)

    return items


def registry_catalog(
    enabled: set[str],
    *,
    user: Any | None = None,
    allowed_modules: set[str] | None = None,
    active_role: str | None = None,
    public_base: str | None = None,
) -> dict[str, Any]:
    """Catalog: tenant + profile + modules + aggregated MODULE_CONTRACT exports."""
    from modoor.platform.services import aggregated_exports

    from modoor.core.settings import public_module_gate

    settings = get_settings()
    base = public_module_gate(settings.modoor_webui_url) or (public_base or "").rstrip("/")
    tenant_id = getattr(user, "tenant", None)
    tenant_name = settings.modoor_tenant
    access = {"unrestricted": False, "abilities": []}
    menu_layouts: dict[str, str] = {}
    industry = "all"
    if tenant_id is not None:
        from modoor.core.ctx import Ctx
        from modoor.core.db import session_scope
        from inbuilt.base.domain import SystemTenant, access_gate

        with session_scope() as session:
            row = session.get(SystemTenant, int(tenant_id))
            if row is not None:
                tenant_name = row.name
            if user is not None and getattr(user, "id", None):
                access = access_gate(
                    session,
                    Ctx(
                        tenant=int(user.tenant),
                        user_id=int(user.id),
                        team_id=getattr(user, "team_id", None),
                    ),
                    user_id=int(user.id),
                    active_role=active_role,
                )
            from inbuilt.base.global_settings import get_menu_layouts

            menu_layouts = get_menu_layouts(
                session,
                Ctx(tenant=int(tenant_id), user_id=0, team_id=0),
            )
            industry = _tenant_menu_industry(session, int(tenant_id))
    else:
        from modoor.core.ctx import Ctx
        from modoor.core.db import session_scope
        from inbuilt.base.domain import ensure_tenant

        with session_scope() as session:
            tenant_id = int(
                ensure_tenant(
                    session, tenant_name, tenant_id=settings.modoor_tenant_id
                )["tenant"]["id"]
            )
            from inbuilt.base.global_settings import get_menu_layouts

            menu_layouts = get_menu_layouts(
                session,
                Ctx(tenant=int(tenant_id), user_id=0, team_id=0),
            )
            industry = _tenant_menu_industry(session, int(tenant_id))
    modules = mark_blend_listing(
        merge_blended_menus(switcher_items(enabled, allowed_modules=allowed_modules))
    )
    for item in modules:
        item.pop("replace", None)
        item["menuLayout"] = menu_layouts.get(text(item.get("id")), "top")
        menus = item.get("menus")
        if menus:
            item["menus"] = filter_menus_by_industry(list(menus), industry)
    return {
        "tenant": {
            "id": tenant_id,
            "name": tenant_name,
        },
        "profile": profile_dict(user),
        "modoor_url": base,
        "logout_url": f"{base}/logout" if base else "/logout",
        "modules": modules,
        "exports": aggregated_exports(),
        "access": access,
    }
