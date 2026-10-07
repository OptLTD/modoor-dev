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

# re-export for callers / tests
__all__ = ["APP_LABEL_KEY"]


def _menu_path(raw: dict[str, Any]) -> str:
    return str(raw.get("path") or raw.get("route") or "").strip()


def _normalize_menu(raw: dict[str, Any], *, mid: str, fallback_id: str) -> dict[str, Any] | None:
    """Leaf needs path; group needs items. Nested ``items`` (alias ``children``) supported."""
    items_raw = list(raw.get("items") or raw.get("children") or [])
    items_raw.sort(key=lambda m: (int(m.get("seqno", 100) or 100), m.get("label") or ""))
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
    menu_id = str(raw.get("id") or fallback_id)
    if not path and not items:
        return None
    item: dict[str, Any] = {
        "id": menu_id,
        "label": raw.get("label") or menu_id or "Menu",
        "seqno": int(raw.get("seqno", 100) or 100),
    }
    if path:
        item["path"] = path
    if items:
        item["items"] = items
    return item


def _first_leaf_path(menus: list[dict[str, Any]]) -> str:
    for m in menus:
        path = str(m.get("path") or "").strip()
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
        if str(m.get("id") or "") == menu_id:
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
            kids.sort(key=lambda m: (int(m.get("seqno", 100) or 100), m.get("label") or ""))
            group["items"] = kids
            return
    host_menus.extend(contrib)
    host_menus.sort(key=lambda m: (int(m.get("seqno", 100) or 100), m.get("label") or ""))


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
        kind = (ui.get("kind") or "app").strip()
        # External apps must register at runtime — do not load from modules/
        if kind == "external":
            continue
        menus_raw = list(exports.get("menus") or [])
        menus_raw.sort(key=lambda m: (int(m.get("seqno", 100) or 100), m.get("label") or ""))
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
        try:
            seqno = int(ui.get("seqno", 1000))
        except (TypeError, ValueError):
            seqno = 1000

        # Extension packages contribute menus/i18n into host; not a switcher app.
        if kind == "extension":
            host = str(ui.get("host") or "").strip()
            parent = str(ui.get("parent") or "").strip() or None
            if host:
                pending_ext.append((host, {"parent": parent}, menus, top_i18n if isinstance(top_i18n, dict) else {}))
            continue

        pkg = str(meta.get("pkg") or "")
        if pkg == "builtin":
            origin = "builtin"
        elif pkg == "lightapp":
            origin = "lightapp"
        else:
            origin = "addon"
        catalog[mid] = {
            "id": mid,
            "label": ui.get("label") or mid.title(),
            "i18n": top_i18n,
            "kind": kind,
            "seqno": seqno,
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
    api_base = modoor_base_url()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    order = sorted(
        catalog.keys(),
        key=lambda mid: (int(catalog[mid].get("seqno", 1000)), mid),
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
            href = f"{api_base}{path}"
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
                "seqno": int(meta.get("seqno", 1000)),
                "entry": href, "menus": menus,
                "exports": None, "online": True,
                "exports_count": None,
                "source": "module",
                "origin": meta.get("origin") or "addon",
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
        href = f"{api_base}/go/{mid}"
        exports = (svc.get("manifest") or {}).get("exports") or {}
        arts = svc.get("artifacts") or {}
        mfest = svc.get("manifest") or {}
        ui = mfest.get("ui-web") or {}
        if not isinstance(ui, dict):
            ui = {}
        try:
            seqno = int(ui.get("seqno", 2000))
        except (TypeError, ValueError):
            seqno = 2000
        items.append(
            {
                "id": mid,
                "label": svc.get("app_name") or ui.get("label") or mid,
                "i18n": normalize_manifest_i18n(mfest.get("i18n")),
                "href": href,
                "kind": "external",
                "seqno": seqno,
                "online": bool(svc.get("online", True)),
                "entry": svc.get("entry_url"),
                "exports": exports,
                "exports_count": {
                    "tools": len(exports.get("tools") or []),
                    "skills": len(exports.get("skills") or []),
                    "models": len(arts.get("models") or []),
                },
                "source": "external",
                "origin": "addon",
            }
        )
        seen.add(mid)

    return items


def registry_catalog(
    enabled: set[str],
    *,
    user: Any | None = None,
    allowed_modules: set[str] | None = None,
) -> dict[str, Any]:
    """Catalog: tenant + profile + modules + aggregated MODULE_CONTRACT exports."""
    from modoor.platform.services import aggregated_exports

    settings = get_settings()
    base = modoor_base_url()
    tenant_id = getattr(user, "tenant", None)
    tenant_name = settings.modoor_tenant
    if tenant_id is not None:
        from modoor.core.db import session_scope
        from builtin.base.domain import SystemTenant

        with session_scope() as session:
            row = session.get(SystemTenant, int(tenant_id))
            if row is not None:
                tenant_name = row.name
    else:
        from modoor.core.db import session_scope
        from builtin.base.domain import ensure_tenant

        with session_scope() as session:
            tenant_id = int(
                ensure_tenant(
                    session, tenant_name, tenant_id=settings.modoor_tenant_id
                )["tenant"]["id"]
            )
    return {
        "tenant": {
            "id": tenant_id,
            "name": tenant_name,
        },
        "profile": profile_dict(user),
        "modoor_url": base,
        "logout_url": f"{base}/logout",
        "modules": switcher_items(enabled, allowed_modules=allowed_modules),
        "exports": aggregated_exports(),
    }
