from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.ctx import Ctx
from modoor.core.db import Base
from modoor.core.errors import AppError

SOURCE_MODULE = "module"
SOURCE_CUSTOM = "custom"
SOURCE_OVERRIDE = "override"
CUSTOM_MODULE_ID = "custom"
READONLY_MODULE = "base"


class SkillItem(Base):
    __tablename__ = "skill_item"
    __table_args__ = (
        UniqueConstraint(
            "tenant", "module", "skill_key", name="uq_skill_item_tenant_module_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    module: Mapped[str] = mapped_column(String(64), index=True, default=CUSTOM_MODULE_ID)
    skill_key: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    when_to_use: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    tools_json: Mapped[str] = mapped_column(Text, default="[]")
    confirmations_json: Mapped[str] = mapped_column(Text, default="[]")
    boundaries: Mapped[str] = mapped_column(Text, default="")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _normalize_key(skill_key: str) -> str:
    value = skill_key.strip().lower().replace("-", "_").replace(" ", "_")
    if not value:
        raise AppError("validation_error", "skill_key is required")
    if not _KEY_RE.match(value):
        raise AppError(
            "validation_error",
            "skill_key must be lowercase letters/digits/underscore, start with a letter",
        )
    return value


def _normalize_module(module: str) -> str:
    value = (module or CUSTOM_MODULE_ID).strip().lower().replace("-", "_")
    if not value:
        value = CUSTOM_MODULE_ID
    if not _MODULE_RE.match(value):
        raise AppError("validation_error", "module id is invalid")
    return value


def _skill_id(module: str, skill_key: str) -> str:
    return f"{module}.{skill_key}"


def _parse_skill_id(skill_id: str) -> tuple[str, str]:
    sid = (skill_id or "").strip()
    if "." not in sid:
        raise AppError("validation_error", "skill_id must be module.skill_key")
    module, skill_key = sid.split(".", 1)
    return _normalize_module(module), _normalize_key(skill_key)


def _is_readonly_module(module: str) -> bool:
    return _normalize_module(module) == READONLY_MODULE


def _loads_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _dumps_list(value: list[Any] | None) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _parse_skill_md(text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            loaded = yaml.safe_load(parts[1]) or {}
            if isinstance(loaded, dict):
                meta = loaded
            body = parts[2].lstrip("\n")
    return {**meta, "content": body}


def _render_skill_md(payload: dict[str, Any]) -> str:
    front = {
        "id": payload.get("id"),
        "title": payload.get("title") or "",
        "summary": payload.get("summary") or "",
        "when_to_use": payload.get("when_to_use") or "",
        "tools": payload.get("tools") or [],
        "confirmations": payload.get("confirmations") or [],
    }
    if payload.get("boundaries"):
        front["boundaries"] = payload["boundaries"]
    body = (payload.get("content") or "").strip()
    dumped = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{dumped}\n---\n\n{body}\n"


def _row_to_dict(
    row: SkillItem,
    *,
    include_content: bool = True,
    has_module_file: bool = False,
) -> dict[str, Any]:
    module = row.module or CUSTOM_MODULE_ID
    sid = _skill_id(module, row.skill_key)
    if module == CUSTOM_MODULE_ID:
        source = SOURCE_CUSTOM
    elif has_module_file:
        source = SOURCE_OVERRIDE
    else:
        source = SOURCE_CUSTOM
    data: dict[str, Any] = {
        "id": sid,
        "record_id": row.id,
        "source": source,
        "overridden": module != CUSTOM_MODULE_ID and has_module_file,
        "readonly": _is_readonly_module(module),
        "module": module,
        "skill_key": row.skill_key,
        "title": row.title,
        "summary": row.summary or "",
        "when_to_use": row.when_to_use or "",
        "tools": _loads_list(row.tools_json),
        "confirmations": _loads_list(row.confirmations_json),
        "boundaries": row.boundaries or "",
        "disabled": bool(row.disabled),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "uri": f"skill://{module}/{row.skill_key}",
    }
    if include_content:
        data["content"] = row.content or ""
        data["markdown"] = _render_skill_md(data)
    return data


def _module_skill_paths() -> list[Path]:
    from modoor.platform.roots import module_pkg_roots

    paths: list[Path] = []
    for _pkg, root in module_pkg_roots():
        if not root.is_dir():
            continue
        paths.extend(sorted(root.glob("*/skills/*.md")))
    return paths


def _read_module_skill(path: Path) -> dict[str, Any]:
    module_id = path.parent.parent.name
    skill_name = path.stem
    raw = path.read_text(encoding="utf-8")
    parsed = _parse_skill_md(raw)
    skill_id = str(parsed.get("id") or f"{module_id}.{skill_name}")
    return {
        "id": skill_id,
        "source": SOURCE_MODULE,
        "overridden": False,
        "readonly": _is_readonly_module(module_id),
        "module": module_id,
        "skill_key": skill_name,
        "title": str(parsed.get("title") or skill_name),
        "summary": str(parsed.get("summary") or ""),
        "when_to_use": str(parsed.get("when_to_use") or ""),
        "tools": list(parsed.get("tools") or [])
        if isinstance(parsed.get("tools"), list)
        else [],
        "confirmations": list(parsed.get("confirmations") or [])
        if isinstance(parsed.get("confirmations"), list)
        else [],
        "boundaries": str(parsed.get("boundaries") or ""),
        "disabled": False,
        "content": str(parsed.get("content") or ""),
        "markdown": raw,
        "uri": f"skill://{module_id}/{skill_name}",
        "path": str(path),
        "updated_at": None,
    }


def list_module_skills(*, q: str | None = None) -> list[dict[str, Any]]:
    needle = (q or "").strip().lower()
    items: list[dict[str, Any]] = []
    for path in _module_skill_paths():
        item = _read_module_skill(path)
        slim = {k: v for k, v in item.items() if k not in ("content", "markdown")}
        if needle:
            blob = " ".join(
                [
                    slim.get("id") or "",
                    slim.get("title") or "",
                    slim.get("summary") or "",
                    slim.get("module") or "",
                    slim.get("skill_key") or "",
                ]
            ).lower()
            if needle not in blob:
                continue
        items.append(slim)
    return items


def get_module_skill(
    *, skill_id: str | None = None, module: str | None = None, skill_key: str | None = None
) -> dict[str, Any]:
    if skill_id and "." in skill_id:
        module, skill_key = skill_id.split(".", 1)
    if not module or not skill_key:
        raise AppError("validation_error", "module+skill_key or skill_id is required")
    if module == CUSTOM_MODULE_ID:
        raise AppError("not_found", "Not a module-exported skill")
    from modoor.platform.roots import module_dir

    path = module_dir(module) / "skills" / f"{skill_key}.md"
    if not path.is_file():
        raise AppError("not_found", f"Module skill not found: {module}.{skill_key}")
    return _read_module_skill(path)


def _scope_query(ctx: Ctx):
    return select(SkillItem).where(SkillItem.tenant == ctx.tenant)


def _get_row(
    session: Session,
    ctx: Ctx,
    *,
    record_id: str | None = None,
    module: str | None = None,
    skill_key: str | None = None,
    skill_id: str | None = None,
) -> SkillItem:
    if skill_id:
        module, skill_key = _parse_skill_id(skill_id)
    if record_id:
        row = session.get(SkillItem, record_id)
    elif module and skill_key:
        row = session.scalar(
            select(SkillItem).where(
                SkillItem.tenant == ctx.tenant,
                SkillItem.module == _normalize_module(module),
                SkillItem.skill_key == _normalize_key(skill_key),
            )
        )
    else:
        raise AppError("validation_error", "record_id or skill_id required")

    if row is None or row.tenant != ctx.tenant:
        raise AppError("not_found", "Skill not found in database")
    return row


def _module_file_exists(module: str, skill_key: str) -> bool:
    if module == CUSTOM_MODULE_ID:
        return False
    from modoor.platform.roots import module_dir

    return (module_dir(module) / "skills" / f"{skill_key}.md").is_file()


def list_skills(
    session: Session,
    ctx: Ctx,
    *,
    source: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Merge on-disk module skills with tenant DB rows (DB wins for same id)."""
    if source is not None and source not in (
        SOURCE_MODULE,
        SOURCE_CUSTOM,
        SOURCE_OVERRIDE,
    ):
        raise AppError("validation_error", "invalid source filter")

    by_id: dict[str, dict[str, Any]] = {}
    for item in list_module_skills(q=None):
        by_id[str(item["id"])] = item

    rows = list(
        session.scalars(
            _scope_query(ctx).order_by(SkillItem.module.asc(), SkillItem.skill_key.asc())
        )
    )
    for row in rows:
        has_file = _module_file_exists(row.module, row.skill_key)
        if _is_readonly_module(row.module) and has_file:
            # base: keep file metadata in list, only overlay disabled / record_id
            sid = _skill_id(row.module, row.skill_key)
            base_item = by_id.get(sid)
            if base_item is None:
                continue
            base_item = dict(base_item)
            base_item["disabled"] = bool(row.disabled)
            base_item["record_id"] = row.id
            base_item["updated_at"] = (
                row.updated_at.isoformat() if row.updated_at else None
            )
            by_id[sid] = base_item
            continue
        overlay = _row_to_dict(row, include_content=False, has_module_file=has_file)
        by_id[str(overlay["id"])] = overlay

    items = list(by_id.values())
    if source == SOURCE_MODULE:
        items = [x for x in items if x.get("source") == SOURCE_MODULE]
    elif source == SOURCE_CUSTOM:
        items = [x for x in items if x.get("module") == CUSTOM_MODULE_ID]
    elif source == SOURCE_OVERRIDE:
        items = [x for x in items if x.get("source") == SOURCE_OVERRIDE]

    needle = (q or "").strip().lower()
    if needle:
        filtered: list[dict[str, Any]] = []
        for slim in items:
            blob = " ".join(
                [
                    str(slim.get("id") or ""),
                    str(slim.get("title") or ""),
                    str(slim.get("summary") or ""),
                    str(slim.get("module") or ""),
                    str(slim.get("skill_key") or ""),
                ]
            ).lower()
            if needle in blob:
                filtered.append(slim)
        items = filtered

    items.sort(key=lambda x: (str(x.get("module") or ""), str(x.get("skill_key") or "")))
    if limit > 0:
        items = items[:limit]
    return {"items": items, "count": len(items)}


def get_skill(
    session: Session,
    ctx: Ctx,
    *,
    skill_id: str | None = None,
    source: str | None = None,
    module: str | None = None,
    skill_key: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    if record_id:
        row = _get_row(session, ctx, record_id=record_id)
        return _row_to_dict(
            row,
            include_content=True,
            has_module_file=_module_file_exists(row.module, row.skill_key),
        )

    if skill_id:
        module, skill_key = _parse_skill_id(skill_id)
    elif module and skill_key:
        module = _normalize_module(module)
        skill_key = _normalize_key(skill_key)
    else:
        raise AppError("validation_error", "skill_id or module+skill_key is required")

    # Tenant DB always wins for non-base (and custom).
    row = session.scalar(
        select(SkillItem).where(
            SkillItem.tenant == ctx.tenant,
            SkillItem.module == module,
            SkillItem.skill_key == skill_key,
        )
    )
    if row is not None:
        if _is_readonly_module(module):
            # base: file content wins; still surface tenant disabled flag.
            file_skill = get_module_skill(module=module, skill_key=skill_key)
            file_skill["disabled"] = bool(row.disabled)
            file_skill["record_id"] = row.id
            file_skill["updated_at"] = (
                row.updated_at.isoformat() if row.updated_at else None
            )
            return file_skill
        return _row_to_dict(
            row,
            include_content=True,
            has_module_file=_module_file_exists(module, skill_key),
        )

    if module == CUSTOM_MODULE_ID:
        raise AppError("not_found", f"Skill not found: {module}.{skill_key}")

    file_skill = get_module_skill(module=module, skill_key=skill_key)
    if source == SOURCE_CUSTOM:
        raise AppError("not_found", "Not a custom skill")
    return file_skill


def upsert_skill(
    session: Session,
    ctx: Ctx,
    *,
    skill_id: str | None = None,
    module: str | None = None,
    skill_key: str | None = None,
    title: str,
    summary: str = "",
    when_to_use: str = "",
    content: str = "",
    tools: list[Any] | None = None,
    confirmations: list[Any] | None = None,
    boundaries: str = "",
    record_id: str | None = None,
    disabled: bool | None = None,
) -> dict[str, Any]:
    """Create or update a skill row. Base module skills cannot be written."""
    if record_id:
        row = _get_row(session, ctx, record_id=record_id)
        module = row.module
        skill_key = row.skill_key
    elif skill_id:
        module, skill_key = _parse_skill_id(skill_id)
    else:
        module = _normalize_module(module or CUSTOM_MODULE_ID)
        skill_key = _normalize_key(skill_key or "")

    if _is_readonly_module(module):
        raise AppError(
            "permission_denied",
            "base module skills are read-only",
            details={"module": module, "skill_key": skill_key},
        )

    title = (title or "").strip()
    if not title:
        raise AppError("validation_error", "title is required")

    row = session.scalar(
        select(SkillItem).where(
            SkillItem.tenant == ctx.tenant,
            SkillItem.module == module,
            SkillItem.skill_key == skill_key,
        )
    )
    if row is None:
        row = SkillItem(
            id=str(uuid.uuid4()),
            tenant=ctx.tenant,
            team_id=ctx.team_id,
            module=module,
            skill_key=skill_key,
            title=title,
            summary=summary or "",
            when_to_use=when_to_use or "",
            content=content or "",
            tools_json=_dumps_list(tools),
            confirmations_json=_dumps_list(confirmations),
            boundaries=boundaries or "",
            disabled=bool(disabled) if disabled is not None else False,
            created_by=ctx.user_id,
            updated_by=ctx.user_id,
        )
        session.add(row)
    else:
        row.title = title
        row.summary = summary or ""
        row.when_to_use = when_to_use or ""
        row.content = content or ""
        row.tools_json = _dumps_list(tools)
        row.confirmations_json = _dumps_list(confirmations)
        row.boundaries = boundaries or ""
        if disabled is not None:
            row.disabled = bool(disabled)
        row.updated_by = ctx.user_id
        row.updated_at = datetime.now(timezone.utc)

    session.flush()
    return _row_to_dict(
        row,
        include_content=True,
        has_module_file=_module_file_exists(module, skill_key),
    )


def set_skill_disabled(
    session: Session,
    ctx: Ctx,
    *,
    skill_id: str,
    disabled: bool,
) -> dict[str, Any]:
    """Enable/disable a skill. Module-synced skills can be disabled but not deleted."""
    sid = (skill_id or "").strip()
    if not sid:
        raise AppError("validation_error", "skill_id required")
    module, skill_key = _parse_skill_id(sid)
    current = get_skill(session, ctx, skill_id=sid)

    row = session.scalar(
        select(SkillItem).where(
            SkillItem.tenant == ctx.tenant,
            SkillItem.module == module,
            SkillItem.skill_key == skill_key,
        )
    )
    if row is None:
        # Persist a tenant row so disabled state sticks (incl. base / module files).
        row = SkillItem(
            id=str(uuid.uuid4()),
            tenant=ctx.tenant,
            team_id=ctx.team_id,
            module=module,
            skill_key=skill_key,
            title=str(current.get("title") or skill_key),
            summary=str(current.get("summary") or ""),
            when_to_use=str(current.get("when_to_use") or ""),
            content=str(current.get("content") or ""),
            tools_json=_dumps_list(list(current.get("tools") or [])),
            confirmations_json=_dumps_list(list(current.get("confirmations") or [])),
            boundaries=str(current.get("boundaries") or ""),
            disabled=bool(disabled),
            created_by=ctx.user_id,
            updated_by=ctx.user_id,
        )
        session.add(row)
    else:
        row.disabled = bool(disabled)
        row.updated_by = ctx.user_id
        row.updated_at = datetime.now(timezone.utc)
    session.flush()

    if _is_readonly_module(module):
        file_skill = get_module_skill(module=module, skill_key=skill_key)
        file_skill["disabled"] = bool(row.disabled)
        file_skill["record_id"] = row.id
        return file_skill
    return _row_to_dict(
        row,
        include_content=True,
        has_module_file=_module_file_exists(module, skill_key),
    )


def delete_skill(
    session: Session,
    ctx: Ctx,
    *,
    record_id: str | None = None,
    skill_key: str | None = None,
    skill_id: str | None = None,
) -> dict[str, Any]:
    """Delete a custom skill row. Module-synced skills cannot be deleted (disable instead)."""
    if skill_id:
        module, key = _parse_skill_id(skill_id)
        if _module_file_exists(module, key):
            raise AppError(
                "permission_denied",
                "module-synced skills cannot be deleted; disable them instead",
            )
        if _is_readonly_module(module):
            raise AppError("permission_denied", "base module skills are read-only")
    row = _get_row(
        session, ctx, record_id=record_id, skill_key=skill_key, skill_id=skill_id
    )
    if _module_file_exists(row.module, row.skill_key):
        raise AppError(
            "permission_denied",
            "module-synced skills cannot be deleted; disable them instead",
        )
    if _is_readonly_module(row.module):
        raise AppError("permission_denied", "base module skills are read-only")
    if row.module != CUSTOM_MODULE_ID:
        raise AppError(
            "permission_denied",
            "only custom skills can be deleted",
        )
    payload = _row_to_dict(
        row,
        include_content=False,
        has_module_file=False,
    )
    session.delete(row)
    session.flush()
    return {"deleted": True, "skill": payload}


# --- backward-compatible aliases used by agent_routes / older callers ---


def create_skill(
    session: Session,
    ctx: Ctx,
    *,
    skill_key: str,
    title: str,
    summary: str = "",
    when_to_use: str = "",
    content: str = "",
    tools: list[Any] | None = None,
    confirmations: list[Any] | None = None,
    boundaries: str = "",
    module: str | None = None,
) -> dict[str, Any]:
    return upsert_skill(
        session,
        ctx,
        module=module or CUSTOM_MODULE_ID,
        skill_key=skill_key,
        title=title,
        summary=summary,
        when_to_use=when_to_use,
        content=content,
        tools=tools,
        confirmations=confirmations,
        boundaries=boundaries,
    )


def update_skill(
    session: Session,
    ctx: Ctx,
    *,
    record_id: str | None = None,
    skill_key: str | None = None,
    skill_id: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    when_to_use: str | None = None,
    content: str | None = None,
    tools: list[Any] | None = None,
    confirmations: list[Any] | None = None,
    boundaries: str | None = None,
    new_skill_key: str | None = None,
) -> dict[str, Any]:
    row = _get_row(
        session, ctx, record_id=record_id, skill_key=skill_key, skill_id=skill_id
    )
    if _is_readonly_module(row.module):
        raise AppError("permission_denied", "base module skills are read-only")
    if new_skill_key is not None and _normalize_key(new_skill_key) != row.skill_key:
        raise AppError("validation_error", "renaming skill_key is not supported")
    return upsert_skill(
        session,
        ctx,
        record_id=row.id,
        title=title if title is not None else row.title,
        summary=summary if summary is not None else (row.summary or ""),
        when_to_use=when_to_use if when_to_use is not None else (row.when_to_use or ""),
        content=content if content is not None else (row.content or ""),
        tools=tools if tools is not None else _loads_list(row.tools_json),
        confirmations=confirmations
        if confirmations is not None
        else _loads_list(row.confirmations_json),
        boundaries=boundaries if boundaries is not None else (row.boundaries or ""),
    )


def get_custom_skill_markdown(
    session: Session, *, tenant: int, skill_key: str
) -> str | None:
    row = session.scalar(
        select(SkillItem).where(
            SkillItem.tenant == tenant,
            SkillItem.module == CUSTOM_MODULE_ID,
            SkillItem.skill_key == skill_key,
        )
    )
    if row is None:
        return None
    return _render_skill_md(
        _row_to_dict(row, include_content=True, has_module_file=False)
    )


def list_custom_skills_for_catalog(
    session: Session, *, tenant: int
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(SkillItem)
        .where(SkillItem.tenant == tenant)
        .order_by(SkillItem.module.asc(), SkillItem.skill_key.asc())
    )
    return [
        {
            "id": _skill_id(row.module, row.skill_key),
            "module": row.module,
            "skill": row.skill_key,
            "uri": f"skill://{row.module}/{row.skill_key}",
            "source": SOURCE_CUSTOM
            if row.module == CUSTOM_MODULE_ID
            else SOURCE_OVERRIDE,
            "title": row.title,
            "readonly": _is_readonly_module(row.module),
        }
        for row in rows
    ]
