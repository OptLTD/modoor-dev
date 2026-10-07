"""Discover and load platform + business modules (domain / MCP tools / PC web UI)."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from sqlalchemy.orm import Session

from modoor.core.settings import Settings, get_settings
from modoor.platform.module_state import (
    discover_manifests,
    enabled_module_ids,
    mark_schema_installed,
    yaml_actived_module_ids,
)
from modoor.platform.roots import find_module_dir

log = logging.getLogger("modoor.loader")

_loaded_domains: set[str] = set()


def _module_ids(settings: Settings) -> list[str]:
    return [m["id"] for m in discover_manifests(settings)]


def _manifest_by_id(settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in discover_manifests(settings)}


def _topo_order(module_ids: set[str], settings: Settings | None = None) -> list[str]:
    """Order modules so depends come first. Cycles are broken by skipping missing edges."""
    meta = _manifest_by_id(settings)
    pending = set(module_ids)
    ordered: list[str] = []
    while pending:
        progress = False
        for mid in sorted(pending):
            deps = [d for d in (meta.get(mid) or {}).get("depends") or [] if d in pending]
            if deps:
                continue
            ordered.append(mid)
            pending.discard(mid)
            progress = True
        if not progress:
            ordered.extend(sorted(pending))
            break
    return ordered


def _import_domain(module_id: str, settings: Settings | None = None) -> str | None:
    if module_id in _loaded_domains:
        hit = find_module_dir(module_id, settings)
        if hit is None:
            return None
        return f"{hit[0]}.{module_id}.domain"
    hit = find_module_dir(module_id, settings)
    if hit is None:
        return None
    pkg, root = hit
    domain_py = root / "domain.py"
    domain_pkg = root / "domain" / "__init__.py"
    if not domain_py.is_file() and not domain_pkg.is_file():
        return None
    dotted = f"{pkg}.{module_id}.domain"
    importlib.import_module(dotted)
    _loaded_domains.add(module_id)
    return dotted


def _run_module_migrate(conn, module_id: str, settings: Settings | None = None) -> str | None:
    hit = find_module_dir(module_id, settings)
    if hit is None:
        return None
    pkg, root = hit
    migrate_fn = None
    dotted: str | None = None
    migrate_py = root / "migrate.py"
    if migrate_py.is_file():
        dotted = f"{pkg}.{module_id}.migrate"
        mod = importlib.import_module(dotted)
        migrate_fn = getattr(mod, "migrate", None)
    if migrate_fn is None:
        domain_py = root / "domain.py"
        domain_pkg = root / "domain" / "__init__.py"
        if domain_py.is_file() or domain_pkg.is_file():
            dotted = f"{pkg}.{module_id}.domain"
            mod = importlib.import_module(dotted)
            migrate_fn = getattr(mod, "migrate", None)
    if migrate_fn is None or dotted is None:
        return None
    migrate_fn(conn)
    return dotted


def _call_on_enable(session: Session, module_id: str, ctx: Any) -> None:
    hit = find_module_dir(module_id)
    if hit is None:
        return
    pkg, root = hit
    for rel, dotted in (
        ("install.py", f"{pkg}.{module_id}.install"),
        ("domain.py", f"{pkg}.{module_id}.domain"),
        ("domain/__init__.py", f"{pkg}.{module_id}.domain"),
    ):
        path = root / rel if not rel.endswith("__init__.py") else root / "domain" / "__init__.py"
        if rel == "domain/__init__.py":
            path = root / "domain" / "__init__.py"
        elif rel == "domain.py":
            path = root / "domain.py"
        else:
            path = root / "install.py"
        if not path.is_file():
            continue
        mod = importlib.import_module(dotted)
        fn = getattr(mod, "on_enable", None)
        if callable(fn):
            fn(session, ctx)
            return


def modules_to_load(settings: Settings | None = None) -> set[str]:
    """Modules whose domains should be imported at process boot."""
    settings = settings or get_settings()
    if getattr(settings, "modoor_load_all_modules", False):
        return set(_module_ids(settings))
    return yaml_actived_module_ids(settings)


def load_module_domains(
    settings: Settings | None = None, *, module_ids: set[str] | None = None
) -> list[str]:
    """Import domain packages for enabled (or explicitly listed) modules only."""
    settings = settings or get_settings()
    wanted = module_ids if module_ids is not None else modules_to_load(settings)
    loaded: list[str] = []
    for module_id in _topo_order(wanted, settings):
        dotted = _import_domain(module_id, settings)
        if dotted:
            loaded.append(dotted)
    return loaded


def ensure_module_schema(
    module_id: str,
    *,
    settings: Settings | None = None,
    engine=None,
    session: Session | None = None,
) -> list[str]:
    """Import domain, create tables, migrate, mark app_schema — recursive on depends."""
    from modoor.core.db import Base

    settings = settings or get_settings()
    meta = _manifest_by_id(settings)
    if module_id not in meta and find_module_dir(module_id, settings) is None:
        return []

    deps = [str(d) for d in (meta.get(module_id) or {}).get("depends") or []]
    ran: list[str] = []
    for dep in deps:
        ran.extend(
            ensure_module_schema(dep, settings=settings, engine=engine, session=session)
        )

    if module_id in _loaded_domains or _import_domain(module_id, settings):
        pass

    if engine is None:
        from modoor.core.db import _engine

        engine = _engine
    if engine is not None:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            dotted = _run_module_migrate(conn, module_id, settings)
            if dotted:
                ran.append(dotted)

    version = str((meta.get(module_id) or {}).get("version") or "")
    if session is not None:
        mark_schema_installed(session, module_id, version=version)
    else:
        try:
            from modoor.core.db import session_scope

            with session_scope() as s:
                mark_schema_installed(s, module_id, version=version)
        except Exception:  # noqa: BLE001
            log.debug("mark_schema_installed skipped for %s", module_id, exc_info=True)
    return ran


def ensure_module_enabled(session: Session, tenant: int, module_id: str, *, ctx=None) -> None:
    """Ensure schema exists then run optional on_enable for the tenant."""
    from modoor.core.ctx import Ctx
    from modoor.core.db import _engine
    from modoor.platform.module_state import set_module_enabled

    ensure_module_schema(module_id, engine=_engine, session=session)
    set_module_enabled(session, tenant, module_id, True)
    if ctx is None:
        ctx = Ctx(tenant=tenant, user_id=0, team_id=0)
    _call_on_enable(session, module_id, ctx)


def ensure_modules_ready(
    session: Session, *, settings: Settings | None = None, tenant: int | None = None
) -> list[str]:
    """Install schema for yaml-enabled + any-tenant-enabled modules; on_enable for tenant."""
    from modoor.core.ctx import Ctx
    from modoor.core.db import _engine
    from modoor.platform.module_state import any_tenant_enabled_ids

    settings = settings or get_settings()
    wanted = yaml_actived_module_ids(settings) | any_tenant_enabled_ids(session)
    if getattr(settings, "modoor_load_all_modules", False):
        wanted = set(_module_ids(settings))
    ran: list[str] = []
    for mid in _topo_order(wanted, settings):
        ran.extend(ensure_module_schema(mid, settings=settings, engine=_engine, session=session))
        if tenant is not None:
            from modoor.platform.module_state import AppInstall
            from sqlalchemy import select

            row = session.scalar(
                select(AppInstall).where(
                    AppInstall.tenant == tenant, AppInstall.module_id == mid
                )
            )
            if row is not None and row.enabled:
                _call_on_enable(session, mid, Ctx(tenant=tenant, user_id=0, team_id=0))
    return ran


def register_module_adapters(settings: Settings | None = None) -> list[str]:
    """Import adapters only for modules whose domains are loaded / should load."""
    settings = settings or get_settings()
    wanted = modules_to_load(settings) | set(_loaded_domains)
    loaded: list[str] = []
    for module_id in _topo_order(wanted, settings):
        hit = find_module_dir(module_id, settings)
        if hit is None:
            continue
        pkg, root = hit
        adapters_py = root / "adapters.py"
        if not adapters_py.is_file():
            continue
        dotted = f"{pkg}.{module_id}.adapters"
        importlib.import_module(dotted)
        loaded.append(dotted)
    return loaded


def register_module_migrate(
    conn, settings: Settings | None = None, *, module_ids: set[str] | None = None
) -> list[str]:
    """Run migrate for loaded/enabled modules only."""
    settings = settings or get_settings()
    wanted = module_ids if module_ids is not None else modules_to_load(settings)
    ran: list[str] = []
    for module_id in _topo_order(wanted, settings):
        dotted = _run_module_migrate(conn, module_id, settings)
        if dotted:
            ran.append(dotted)
    return ran


def register_module_tools(mcp: Any, settings: Settings | None = None) -> list[str]:
    """Register MCP tools only for tenant-enabled modules."""
    settings = settings or get_settings()

    enabled: set[str] | None = None
    try:
        from modoor.core.db import session_scope

        with session_scope() as session:
            from builtin.base.domain import ensure_tenant

            tenant_id = int(
                ensure_tenant(
                    session,
                    settings.modoor_tenant,
                    tenant_id=settings.modoor_tenant_id,
                )["tenant"]["id"]
            )
            enabled = enabled_module_ids(session, tenant_id)
    except Exception:  # noqa: BLE001
        enabled = yaml_actived_module_ids(settings)

    registered: list[str] = []
    for module_id in _module_ids(settings):
        if enabled is not None and module_id not in enabled:
            continue
        hit = find_module_dir(module_id, settings)
        if hit is None:
            continue
        pkg, root = hit
        tools_init = root / "tools" / "__init__.py"
        if not tools_init.is_file():
            continue
        dotted = f"{pkg}.{module_id}.tools"
        mod = importlib.import_module(dotted)
        register = getattr(mod, "register", None)
        if register is None:
            continue
        register(mcp)
        registered.append(dotted)
    return registered


def register_module_web(app: Any, kit: Any, settings: Settings | None = None) -> list[str]:
    """Register webui for discovered modules (handlers still check tenant enable)."""
    settings = settings or get_settings()
    registered: list[str] = []
    for module_id in _module_ids(settings):
        hit = find_module_dir(module_id, settings)
        if hit is None:
            continue
        pkg, root = hit
        candidates = [
            (root / "webui.py", f"{pkg}.{module_id}.webui"),
            (root / "web.py", f"{pkg}.{module_id}.web"),
            (root / "ui" / "web.py", f"{pkg}.{module_id}.ui.web"),
        ]
        dotted: str | None = None
        for path, name in candidates:
            if path.is_file():
                dotted = name
                break
        if dotted is None:
            continue
        mod = importlib.import_module(dotted)
        register = getattr(mod, "register", None)
        if register is None:
            continue
        register(app, kit)
        registered.append(dotted)
    return registered


def register_module_jobs(settings: Settings | None = None) -> list[str]:
    """Import jobs.py and call register() for modules that should load."""
    settings = settings or get_settings()
    wanted = modules_to_load(settings) | set(_loaded_domains)
    registered: list[str] = []
    for module_id in _topo_order(wanted, settings):
        hit = find_module_dir(module_id, settings)
        if hit is None:
            continue
        pkg, root = hit
        jobs_py = root / "jobs.py"
        if not jobs_py.is_file():
            continue
        dotted = f"{pkg}.{module_id}.jobs"
        try:
            mod = importlib.import_module(dotted)
        except Exception:  # noqa: BLE001
            log.debug("module jobs import skipped: %s", dotted, exc_info=True)
            continue
        register = getattr(mod, "register", None)
        if register is None:
            continue
        try:
            register()
        except Exception:  # noqa: BLE001
            log.debug("module jobs register skipped: %s", dotted, exc_info=True)
            continue
        registered.append(dotted)
    return registered


def scheduled_jobs_from_manifests(
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Collect exports.jobs with ``every`` (seconds) from modules that should load."""
    settings = settings or get_settings()
    wanted = modules_to_load(settings)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mid in _topo_order(wanted, settings):
        hit = find_module_dir(mid, settings)
        if hit is None:
            continue
        _, root = hit
        path = root / "module.yaml"
        if not path.is_file():
            continue
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        exports = data.get("exports") or {}
        jobs = exports.get("jobs") or []
        if not isinstance(jobs, list):
            continue
        for raw in jobs:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()
            if not kind or kind in seen:
                continue
            every_raw = raw.get("every")
            if every_raw is None:
                continue
            try:
                every = float(every_raw)
            except (TypeError, ValueError):
                continue
            if every <= 0:
                continue
            seen.add(kind)
            out.append({"kind": kind, "every": every, "module_id": mid})
    return out
