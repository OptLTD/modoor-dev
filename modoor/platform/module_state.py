"""Persisted app (module) install / enable state (per tenant)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import yaml
from sqlalchemy import Integer, Boolean, DateTime, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.db import Base
from modoor.core.errors import AppError
from modoor.core.settings import Settings, get_settings
from modoor.platform.manifest_i18n import normalize_manifest_i18n
from modoor.support import flag, seqno, text, texts


class AppInstall(Base):
    """Which on-disk modules/apps are enabled for a tenant."""

    __tablename__ = "app_install"
    __table_args__ = (
        UniqueConstraint("tenant", "module_id", name="uq_app_install_tenant_module"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    module_id: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AppSchema(Base):
    """Global record that a module's ORM tables were created + migrated in this DB."""

    __tablename__ = "app_schema"

    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), default="")
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


def _manifest_actived(data: dict[str, Any]) -> bool:
    """module.yaml ``actived`` (preferred); legacy ``enabled`` accepted."""
    if "actived" in data:
        raw = data.get("actived")
    elif "enabled" in data:
        raw = data.get("enabled")
    else:
        raw = False
    return flag(raw)


def _menu_access_tree(raw: Any) -> list[dict[str, Any]]:
    """Slim menu tree kept for role permissions. ``access`` lists ability codes."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mid = text(item.get("id"), strip=True)
        if not mid:
            continue
        out.append(
            {
                "id": mid,
                "label": text(item.get("label")) or mid,
                "access": texts(item.get("access")),
                "items": _menu_access_tree(item.get("items")),
            }
        )
    return out


def discover_manifests(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    from modoor.platform.roots import module_pkg_roots

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pkg, root in module_pkg_roots(settings):
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/module.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            mid = data.get("id") or path.parent.name
            if mid in seen:
                continue
            seen.add(str(mid))
            ui = data.get("ui-web") or {}
            if not isinstance(ui, dict):
                ui = {}
            kind = text(ui.get("kind")) or "app"
            label = text(ui.get("label")) or mid
            order = seqno(ui.get("seqno"), 1000)
            tags = texts(data.get("tags"))
            # Do not auto-append kind / risk_default / pkg — they clutter filter chips;
            # origin is exposed separately as inbuilt|module|lightapp.
            actived = _manifest_actived(data)
            exports = (data.get("exports") or {}).get("menus")
            items.append(
                {
                    "id": mid,
                    "tags": tags,
                    "label": label,
                    "kind": kind,
                    "seqno": order,
                    "actived": actived,
                    "version": text(data.get("version")),
                    "summary": text(data.get("summary")),
                    "risk_default": text(data.get("risk_default")),
                    "ability": texts(data.get("ability")),
                    "menus": _menu_access_tree(exports),
                    "depends": list(data.get("depends") or []),
                    "tools": (data.get("exports") or {}).get("tools") or [],
                    "skills": (data.get("exports") or {}).get("skills") or [],
                    "i18n": normalize_manifest_i18n(data.get("i18n")),
                    "pkg": pkg, "path": str(path.parent),
                    "blend": text(ui.get("blend"), strip=True),
                }
            )
    items.sort(key=lambda m: (seqno(m.get("seqno"), 1000), text(m.get("id"))))
    return items


def blend_guest_map(settings: Settings | None = None) -> dict[str, str]:
    """Enabled-shape hints: ``guest module id -> host module id`` for ``blend`` manifests.

    A guest rides on the host shell, so permission visibility follows the host.
    """
    out: dict[str, str] = {}
    for meta in discover_manifests(settings):
        guest = text(meta.get("id"), strip=True)
        host = text(meta.get("blend"), strip=True)
        if guest and host:
            out[guest] = host
    return out


def yaml_actived_module_ids(settings: Settings | None = None) -> set[str]:
    return {m["id"] for m in discover_manifests(settings) if m.get("actived")}


# Back-compat alias
yaml_enabled_module_ids = yaml_actived_module_ids


def schema_installed_ids(session: Session) -> set[str]:
    return {row.module_id for row in session.scalars(select(AppSchema))}


def any_tenant_enabled_ids(session: Session) -> set[str]:
    return {
        row.module_id
        for row in session.scalars(select(AppInstall).where(AppInstall.enabled.is_(True)))
    }


def mark_schema_installed(
    session: Session, module_id: str, *, version: str = ""
) -> AppSchema:
    row = session.get(AppSchema, module_id)
    if row is None:
        row = AppSchema(module_id=module_id, version=version or "")
        session.add(row)
    else:
        row.version = version or row.version
        row.installed_at = datetime.now(timezone.utc)
    session.flush()
    return row


def sync_discovered_modules(
    session: Session, tenant: int, settings: Settings | None = None
) -> list[dict[str, Any]]:
    """Ensure an AppInstall row exists for each on-disk module."""
    settings = settings or get_settings()
    discovered = discover_manifests(settings)
    existing = {
        row.module_id: row
        for row in session.scalars(
            select(AppInstall).where(AppInstall.tenant == tenant)
        )
    }
    for item in discovered:
        mid = item["id"]
        row = existing.get(mid)
        if row is None:
            row = AppInstall(
                id=str(uuid.uuid4()),
                tenant=tenant,
                module_id=mid,
                enabled=bool(item.get("actived")),
                version=item["version"],
            )
            session.add(row)
            existing[mid] = row
        else:
            row.version = item["version"]
        row.updated_at = datetime.now(timezone.utc)
    _sync_external_installs(session, tenant, existing)
    session.flush()
    return list_modules(session, tenant, settings=settings)


def _sync_external_installs(
    session: Session, tenant: int, existing: dict[str, AppInstall]
) -> None:
    from modoor.platform.services import list_persisted

    for rec in list_persisted(session):
        mid = rec.module_id
        if not mid or mid in existing:
            continue
        version = text((rec.manifest or {}).get("version"))
        mfest = rec.manifest or {}
        row = AppInstall(
            id=str(uuid.uuid4()),
            tenant=tenant,
            module_id=mid,
            enabled=True,  # explicit external registry install
            version=version,
        )
        session.add(row)
        existing[mid] = row


def ensure_external_install(session: Session, module_id: str, *, version: str = "") -> None:
    """Create AppInstall for a registered external module; do not re-enable if disabled."""
    from inbuilt.base.domain import SystemTenant

    tenant_ids = [int(t.id) for t in session.scalars(select(SystemTenant))]
    if not tenant_ids:
        return
    have = {
        row.tenant
        for row in session.scalars(
            select(AppInstall).where(AppInstall.module_id == module_id)
        )
    }
    for tid in tenant_ids:
        if tid in have:
            continue
        session.add(
            AppInstall(
                id=str(uuid.uuid4()),
                tenant=tid,
                module_id=module_id,
                enabled=True,  # registering an external app activates it
                version=version,
            )
        )


def drop_external_install(session: Session, module_id: str) -> None:
    rows = list(
        session.scalars(select(AppInstall).where(AppInstall.module_id == module_id))
    )
    for row in rows:
        session.delete(row)


def list_modules(
    session: Session, tenant: int, settings: Settings | None = None
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    discovered = {m["id"]: m for m in discover_manifests(settings)}
    rows = {
        r.module_id: r
        for r in session.scalars(
            select(AppInstall).where(AppInstall.tenant == tenant)
        )
    }
    out: list[dict[str, Any]] = []
    for mid, meta in discovered.items():
        row = rows.get(mid)
        if row is None:
            enabled = bool(meta.get("actived"))
        else:
            enabled = bool(row.enabled)
        out.append(
            {
                **meta,
                "enabled": enabled,
                "install_id": row.id if row else None,
                "online": True,
                "source": "module",
                "origin": _module_origin(meta),
                "tags": _module_tags(meta, enabled=enabled),
            }
        )
    from modoor.platform.services import list_persisted, live_service_ids

    live = live_service_ids()
    for rec in list_persisted(session):
        mid = rec.module_id
        if not mid or mid in discovered:
            continue
        row = rows.get(mid)
        enabled = False if row is None else bool(row.enabled)
        mfest = rec.manifest or {}
        ui = mfest.get("ui-web") or {}
        if not isinstance(ui, dict):
            ui = {}
        order = seqno(ui.get("seqno"), 2000)
        online = rec.service_id in live
        meta = {
            "id": mid,
            "label": rec.app_name or ui.get("label") or mid,
            "kind": "external",
            "seqno": order,
            "version": text(mfest.get("version")),
            "summary": mfest.get("summary") or "",
            "tags": ["external"],
            "risk_default": text(mfest.get("risk_default")),
            "ability": texts(mfest.get("ability")),
            "depends": list(mfest.get("depends") or []),
            "actived": _manifest_actived(mfest),
            "tools": (mfest.get("exports") or {}).get("tools") or [],
            "skills": (mfest.get("exports") or {}).get("skills") or [],
            "i18n": normalize_manifest_i18n(mfest.get("i18n")),
            "path": "",
            "pkg": "external",
        }
        out.append(
            {
                **meta,
                "enabled": enabled,
                "install_id": row.id if row else None,
                "online": online,
                "source": "external",
                "origin": "module",
                "tags": _module_tags(meta, enabled=enabled, online=online),
            }
        )
    out.sort(key=lambda m: (seqno(m.get("seqno"), 1000), text(m.get("id"))))
    return drop_blended_hosts(out)


def drop_blended_hosts(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop a module that an enabled module blends into, so the pair shows as one."""
    hidden: set[str] = set()
    for mod in modules:
        if mod.get("enabled") is False:
            continue
        target = text(mod.get("blend"), strip=True)
        if target:
            hidden.add(target)
    if not hidden:
        return modules
    return [mod for mod in modules if text(mod.get("id")) not in hidden]


def _module_origin(meta: dict[str, Any]) -> str:
    """inbuilt / module / lightapp. External registry apps are module; lightapp is tenant-built only."""
    pkg = text(meta.get("pkg"), strip=True)
    if pkg == "inbuilt":
        return "inbuilt"
    if pkg == "lightapp":
        return "lightapp"
    return "module"


def _module_tags(
    meta: dict[str, Any],
    *,
    enabled: bool,
    online: bool | None = None,
) -> list[str]:
    tags = texts(meta.get("tags"))
    status = "enabled" if enabled else "disabled"
    if status not in tags:
        tags.append(status)
    if online is not None:
        liveness = "online" if online else "offline"
        if liveness not in tags:
            tags.append(liveness)
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def enabled_module_ids(session: Session, tenant: int) -> set[str]:
    rows = list(
        session.scalars(select(AppInstall).where(AppInstall.tenant == tenant))
    )
    if not rows:
        # Pre-sync: honor yaml actived defaults only (missing = false).
        enabled = yaml_actived_module_ids()
    else:
        enabled = {r.module_id for r in rows if r.enabled}
    # A blended guest has no shell of its own: bring the host in with it so the
    # pair renders as one app, even when the host row was left disabled.
    guests = blend_guest_map()
    while True:
        hosts = {host for guest, host in guests.items() if guest in enabled} - enabled
        if not hosts:
            return enabled
        enabled |= hosts


def set_module_enabled(
    session: Session, tenant: int, module_id: str, enabled: bool
) -> dict[str, Any]:
    discovered = {m["id"]: m for m in discover_manifests()}
    from modoor.platform.services import AppRegistry

    if module_id not in discovered:
        reg = session.scalar(
            select(AppRegistry).where(AppRegistry.module_id == module_id)
        )
        if reg is None:
            raise AppError("not_found", f"module not found: {module_id}")
        version = text((reg.manifest or {}).get("version"))
    else:
        version = discovered[module_id]["version"]
    row = session.scalar(
        select(AppInstall).where(
            AppInstall.tenant == tenant,
            AppInstall.module_id == module_id,
        )
    )
    if row is None:
        row = AppInstall(
            id=str(uuid.uuid4()),
            tenant=tenant,
            module_id=module_id,
            enabled=enabled,
            version=version,
        )
        session.add(row)
    else:
        row.enabled = enabled
        row.updated_at = datetime.now(timezone.utc)
    session.flush()
    return {
        "module_id": module_id,
        "enabled": row.enabled,
        "version": row.version,
    }
