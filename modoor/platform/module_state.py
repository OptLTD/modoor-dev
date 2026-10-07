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
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


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
            kind = str(ui.get("kind") or "app")
            label = str(ui.get("label") or mid)
            try:
                seqno = int(ui.get("seqno", 1000))
            except (TypeError, ValueError):
                seqno = 1000
            raw_tags = data.get("tags")
            tags: list[str] = []
            if isinstance(raw_tags, list):
                tags = [str(t).strip() for t in raw_tags if str(t).strip()]
            # Do not auto-append kind / risk_default / pkg — they clutter filter chips;
            # origin is exposed separately as builtin|addon|lightapp.
            actived = _manifest_actived(data)
            items.append(
                {
                    "id": mid,
                    "tags": tags,
                    "label": label,
                    "kind": kind,
                    "seqno": seqno,
                    "actived": actived,
                    "version": str(data.get("version") or ""),
                    "summary": data.get("summary") or "",
                    "risk_default": data.get("risk_default") or "",
                    "ability": [str(x) for x in (data.get("ability") or []) if str(x).strip()],
                    "depends": list(data.get("depends") or []),
                    "tools": (data.get("exports") or {}).get("tools") or [],
                    "skills": (data.get("exports") or {}).get("skills") or [],
                    "i18n": normalize_manifest_i18n(data.get("i18n")),
                    "path": str(path.parent),
                    "pkg": pkg,
                }
            )
    items.sort(key=lambda m: (int(m.get("seqno", 1000)), str(m.get("id") or "")))
    return items


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
        version = str((rec.manifest or {}).get("version") or "")
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
    from builtin.base.domain import SystemTenant

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
        try:
            seqno = int(ui.get("seqno", 2000))
        except (TypeError, ValueError):
            seqno = 2000
        online = rec.service_id in live
        meta = {
            "id": mid,
            "label": rec.app_name or ui.get("label") or mid,
            "kind": "external",
            "seqno": seqno,
            "version": str(mfest.get("version") or ""),
            "summary": mfest.get("summary") or "",
            "tags": ["external"],
            "risk_default": str(mfest.get("risk_default") or ""),
            "ability": [str(x) for x in (mfest.get("ability") or []) if str(x).strip()],
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
                "origin": "addon",
                "tags": _module_tags(meta, enabled=enabled, online=online),
            }
        )
    out.sort(key=lambda m: (int(m.get("seqno", 1000)), str(m.get("id") or "")))
    return out


def _module_origin(meta: dict[str, Any]) -> str:
    """builtin / addon / lightapp. External registry apps are addon; lightapp is tenant-built only."""
    pkg = str(meta.get("pkg") or "").strip()
    if pkg == "builtin":
        return "builtin"
    if pkg == "lightapp":
        return "lightapp"
    return "addon"


def _module_tags(
    meta: dict[str, Any],
    *,
    enabled: bool,
    online: bool | None = None,
) -> list[str]:
    tags = [str(t).strip() for t in (meta.get("tags") or []) if str(t).strip()]
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
        return yaml_actived_module_ids()
    return {r.module_id for r in rows if r.enabled}


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
        version = str((reg.manifest or {}).get("version") or "")
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
