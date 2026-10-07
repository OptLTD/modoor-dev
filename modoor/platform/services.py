"""External app registry — same Module contract as MODULE_CONTRACT.md.

Live services register a **manifest** (module.yaml shape) plus optional
**artifacts** (tool/skill/model bodies). Only names listed in
``exports.tools`` / ``exports.skills`` are L1; artifacts outside exports
are ignored.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy import JSON, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.db import Base, session_scope


def _norm_entry_url(url: str) -> str:
    """Keep origin entries as ``.../``; do not force a trailing slash on paths like ``/monitor``."""
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    path = parsed.path or "/"
    if path in ("", "/"):
        path = "/"
    else:
        path = path.rstrip("/") or "/"
    return urlunparse(parsed._replace(path=path))


def _empty_manifest(module_id: str, app_name: str = "") -> dict[str, Any]:
    return {
        "id": module_id,
        "version": "0.0.0",
        "depends": [],
        "summary": "",
        "exports": {"tools": [], "skills": [], "menus": [], "jobs": []},
        "ability": [],
        "risk_default": "medium",
        "ui-web": {
            "kind": "external",
            "label": app_name or module_id,
        },
    }


def _norm_manifest(raw: dict[str, Any] | None, *, module_id: str, app_name: str) -> dict[str, Any]:
    base = _empty_manifest(module_id, app_name)
    raw = dict(raw or {})
    mid = str(raw.get("id") or module_id).strip() or module_id
    exports_in = dict(raw.get("exports") or {})
    ui_in = dict(raw.get("ui-web") or {})
    ability = raw.get("ability")
    if ability is None:
        ability = raw.get("permissions") or []
    return {
        "id": mid,
        "version": str(raw.get("version") or "0.0.0"),
        "depends": list(raw.get("depends") or []),
        "summary": str(raw.get("summary") or ""),
        "exports": {
            "tools": [str(x) for x in (exports_in.get("tools") or [])],
            "skills": [str(x) for x in (exports_in.get("skills") or [])],
            "menus": list(exports_in.get("menus") or []),
            "jobs": list(exports_in.get("jobs") or []),
        },
        "ability": [str(x) for x in (ability or [])],
        "risk_default": str(raw.get("risk_default") or "medium"),
        "ui-web": {
            "kind": "external",
            "label": ui_in.get("label") or app_name or mid,
            "home": ui_in.get("home") or ui_in.get("entry"),
            "entry": ui_in.get("entry") or ui_in.get("home"),
            "recommends": list(ui_in.get("recommends") or ["module_switcher", "logout"]),
        },
        "category": raw.get("category"),
        "events": list(raw.get("events") or []),
    }


def _norm_tool(item: dict[str, Any]) -> dict[str, Any] | None:
    name = item.get("name")
    if not name:
        return None
    return {
        "name": str(name),
        "description": str(item.get("description") or ""),
        "input_schema": item.get("input_schema") or {"type": "object", "properties": {}},
        "output_schema": item.get("output_schema"),
        "ability": item.get("ability") or item.get("permission"),
        "risk": item.get("risk") or "medium",
        "idempotency": bool(item.get("idempotency", False)),
        "side_effects": item.get("side_effects") or "read",
        "invoke_url": item.get("invoke_url"),
    }


def _norm_skill(item: dict[str, Any]) -> dict[str, Any] | None:
    sid = item.get("id") or item.get("name")
    if not sid:
        return None
    return {
        "id": str(sid),
        "title": str(item.get("title") or sid),
        "summary": str(item.get("summary") or ""),
        "when_to_use": str(item.get("when_to_use") or ""),
        "steps": list(item.get("steps") or []),
        "tools": [str(x) for x in (item.get("tools") or [])],
        "confirmations": list(item.get("confirmations") or []),
        "boundaries": item.get("boundaries") or item.get("禁忌") or item.get("禁忌 / 边界"),
        "content": item.get("content"),
        "content_url": item.get("content_url"),
    }


def _norm_model(item: dict[str, Any]) -> dict[str, Any] | None:
    name = item.get("name") or item.get("id")
    if not name:
        return None
    return {
        "name": str(name),
        "description": str(item.get("description") or ""),
        "fields": list(item.get("fields") or []),
    }


def _norm_artifacts(
    raw: dict[str, Any] | None, *, exports: dict[str, list]
) -> dict[str, list[dict[str, Any]]]:
    """Keep only artifacts whose names appear in manifest exports (L1 rule)."""
    raw = dict(raw or {})
    allowed_tools = set(exports.get("tools") or [])
    allowed_skills = set(exports.get("skills") or [])

    tools: list[dict[str, Any]] = []
    for item in raw.get("tools") or []:
        if not isinstance(item, dict):
            continue
        t = _norm_tool(item)
        if t and t["name"] in allowed_tools:
            tools.append(t)

    skills: list[dict[str, Any]] = []
    for item in raw.get("skills") or []:
        if not isinstance(item, dict):
            continue
        s = _norm_skill(item)
        if not s:
            continue
        if s["id"] not in allowed_skills:
            continue
        # Skill tools must ⊆ exports.tools
        s["tools"] = [n for n in s["tools"] if n in allowed_tools]
        skills.append(s)

    models: list[dict[str, Any]] = []
    for item in raw.get("models") or []:
        if not isinstance(item, dict):
            continue
        m = _norm_model(item)
        if m:
            models.append(m)

    return {"tools": tools, "skills": skills, "models": models}


@dataclass
class ServiceRecord:
    service_id: str
    module_id: str
    app_name: str
    entry_url: str
    health_url: str | None = None
    last_seen: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    # MODULE_CONTRACT: manifest ≈ module.yaml; artifacts ≈ tools/skills/models bodies
    manifest: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {"tools": [], "skills": [], "models": []}
    )

    def touch(self) -> None:
        self.last_seen = datetime.now(timezone.utc).isoformat()

    @property
    def exports(self) -> dict[str, list]:
        return dict((self.manifest or {}).get("exports") or {})


class AppRegistry(Base):
    """Persisted external app registration. Survives process restart and offline gaps."""

    __tablename__ = "app_registry"

    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    module_id: Mapped[str] = mapped_column(String(64), index=True)
    app_name: Mapped[str] = mapped_column(String(128), default="")
    entry_url: Mapped[str] = mapped_column(String(512), default="")
    health_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_seen: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifacts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


_lock = threading.Lock()
_services: dict[str, ServiceRecord] = {}


def _sync_mcp_tools() -> None:
    """Best-effort: remount external invoke_url tools onto the live MCP server."""
    try:
        from modoor.runtime.external_tools import sync_external_mcp_tools
        from modoor.runtime.mcp_server import mcp

        sync_external_mcp_tools(mcp)
    except Exception:  # noqa: BLE001
        pass


def live_service_ids() -> set[str]:
    with _lock:
        return set(_services)


def clear_live_services() -> None:
    """Drop in-process liveness only; persisted rows stay (tests / restart)."""
    with _lock:
        _services.clear()


def _record_from_row(row: AppRegistry) -> ServiceRecord:
    rec = ServiceRecord(
        service_id=row.service_id,
        module_id=row.module_id,
        app_name=row.app_name or row.module_id,
        entry_url=row.entry_url,
        health_url=row.health_url,
        last_seen=row.last_seen or "",
        meta=dict(row.meta or {}),
        manifest=dict(row.manifest or {}),
        artifacts=dict(row.artifacts or {"tools": [], "skills": [], "models": []}),
    )
    return rec


def _apply_row(row: AppRegistry, rec: ServiceRecord) -> None:
    row.module_id = rec.module_id
    row.app_name = rec.app_name
    row.entry_url = rec.entry_url
    row.health_url = rec.health_url
    row.last_seen = rec.last_seen
    row.meta = dict(rec.meta or {})
    row.manifest = dict(rec.manifest or {})
    row.artifacts = dict(rec.artifacts or {"tools": [], "skills": [], "models": []})


def _persist(rec: ServiceRecord, *, ensure_install: bool = True) -> None:
    from modoor.platform.module_state import ensure_external_install

    version = str((rec.manifest or {}).get("version") or "")
    with session_scope() as session:
        row = session.get(AppRegistry, rec.service_id)
        if row is None:
            row = AppRegistry(service_id=rec.service_id)
            session.add(row)
        _apply_row(row, rec)
        if ensure_install:
            ensure_external_install(session, rec.module_id, version=version)


def _load_row(service_id: str) -> ServiceRecord | None:
    with session_scope() as session:
        row = session.get(AppRegistry, service_id)
        if row is None:
            return None
        return _record_from_row(row)


def _load_by_module(module_id: str) -> ServiceRecord | None:
    with session_scope() as session:
        row = session.scalar(
            select(AppRegistry).where(AppRegistry.module_id == module_id)
        )
        if row is None:
            return None
        return _record_from_row(row)


def list_persisted(session: Session | None = None) -> list[ServiceRecord]:
    def _rows(s: Session) -> list[ServiceRecord]:
        return [
            _record_from_row(r)
            for r in s.scalars(select(AppRegistry).order_by(AppRegistry.service_id))
        ]

    if session is not None:
        return _rows(session)
    with session_scope() as s:
        return _rows(s)


def persisted_module_ids(session: Session | None = None) -> set[str]:
    return {r.module_id for r in list_persisted(session) if r.module_id}


def _public_dict(rec: ServiceRecord, *, online: bool) -> dict[str, Any]:
    data = asdict(rec)
    data["online"] = online
    data["source"] = "external"
    return data


def _merged_records() -> list[ServiceRecord]:
    by_id = {r.service_id: r for r in list_persisted()}
    with _lock:
        by_id.update(_services)
    return sorted(by_id.values(), key=lambda r: r.service_id)


def register_service(
    *,
    service_id: str,
    module_id: str,
    app_name: str,
    entry_url: str,
    health_url: str | None = None,
    meta: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> ServiceRecord:
    sid = service_id.strip()
    if not sid or not module_id.strip() or not entry_url.strip():
        raise ValueError("service_id, module_id, entry_url are required")

    mfest = _norm_manifest(manifest, module_id=module_id, app_name=app_name)
    arts = _norm_artifacts(artifacts, exports=mfest["exports"])
    rec = ServiceRecord(
        service_id=sid,
        module_id=mfest["id"],
        app_name=(app_name or (mfest.get("ui-web") or {}).get("label") or mfest["id"]).strip(),
        entry_url=_norm_entry_url(entry_url),
        health_url=health_url,
        meta=dict(meta or {}),
        manifest=mfest,
        artifacts=arts,
    )
    rec.touch()
    with _lock:
        _services[sid] = rec
    _persist(rec, ensure_install=True)
    _sync_mcp_tools()
    return rec


def set_manifest_artifacts(
    service_id: str,
    *,
    manifest: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> ServiceRecord | None:
    rec = get_by_service_id(service_id)
    if rec is None:
        return None
    if manifest is not None:
        rec.manifest = _norm_manifest(
            manifest, module_id=rec.module_id, app_name=rec.app_name
        )
    if artifacts is not None:
        rec.artifacts = _norm_artifacts(artifacts, exports=rec.exports)
    rec.touch()
    with _lock:
        _services[service_id] = rec
    _persist(rec, ensure_install=False)
    _sync_mcp_tools()
    return rec


def heartbeat(
    service_id: str,
    *,
    entry_url: str | None = None,
    manifest: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> ServiceRecord | None:
    rec = get_by_service_id(service_id)
    if rec is None:
        return None
    if entry_url:
        rec.entry_url = _norm_entry_url(entry_url)
    if manifest is not None:
        rec.manifest = _norm_manifest(
            manifest, module_id=rec.module_id, app_name=rec.app_name
        )
    if artifacts is not None:
        rec.artifacts = _norm_artifacts(artifacts, exports=rec.exports)
    rec.touch()
    with _lock:
        _services[service_id] = rec
    _persist(rec, ensure_install=False)
    if artifacts is not None or manifest is not None:
        _sync_mcp_tools()
    return rec


def unregister_service(service_id: str) -> bool:
    from modoor.platform.module_state import drop_external_install

    with _lock:
        found_live = _services.pop(service_id, None) is not None
    with session_scope() as session:
        row = session.get(AppRegistry, service_id)
        if row is None:
            return found_live
        module_id = row.module_id
        session.delete(row)
        session.flush()
        still = session.scalar(
            select(AppRegistry).where(AppRegistry.module_id == module_id)
        )
        if still is None:
            drop_external_install(session, module_id)
    _sync_mcp_tools()
    return True


def list_services() -> list[dict[str, Any]]:
    live = live_service_ids()
    return [_public_dict(r, online=r.service_id in live) for r in _merged_records()]


def get_by_module(module_id: str) -> ServiceRecord | None:
    with _lock:
        for rec in _services.values():
            if rec.module_id == module_id:
                return rec
    return _load_by_module(module_id)


def get_by_service_id(service_id: str) -> ServiceRecord | None:
    with _lock:
        hit = _services.get(service_id)
        if hit is not None:
            return hit
    return _load_row(service_id)


def get_entry_url(module_id: str) -> str | None:
    rec = get_by_module(module_id)
    return rec.entry_url if rec else None


def find_tool(tool_name: str) -> tuple[ServiceRecord, dict[str, Any]] | None:
    for rec in _merged_records():
        if tool_name not in (rec.exports.get("tools") or []):
            continue
        for tool in rec.artifacts.get("tools") or []:
            if tool.get("name") == tool_name:
                return rec, tool
    return None


def find_skill(skill_id: str) -> tuple[ServiceRecord, dict[str, Any]] | None:
    for rec in _merged_records():
        allowed = set(rec.exports.get("skills") or [])
        for skill in rec.artifacts.get("skills") or []:
            sid = skill.get("id")
            if sid not in allowed:
                continue
            if sid == skill_id or skill_id.endswith("." + str(sid).split(".")[-1]):
                return rec, skill
    return None


def aggregated_exports() -> dict[str, Any]:
    """Hub view aligned with MODULE_CONTRACT exports + artifacts."""
    tools: list[dict[str, Any]] = []
    skills: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for rec in _merged_records():
        base = {
            "service_id": rec.service_id,
            "module_id": rec.module_id,
            "app_name": rec.app_name,
            "entry_url": rec.entry_url,
            "source": "external",
        }
        manifests.append({**base, "manifest": rec.manifest})
        for tool in rec.artifacts.get("tools") or []:
            tools.append({**base, **tool})
        for skill in rec.artifacts.get("skills") or []:
            skills.append({**base, **skill})
        for model in rec.artifacts.get("models") or []:
            models.append({**base, **model})
    return {
        "manifests": manifests,
        "tools": tools,
        "skills": skills,
        "models": models,
        "services": list_services(),
    }