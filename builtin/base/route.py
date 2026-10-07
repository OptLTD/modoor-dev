"""builtin.base JSON API for Vue views."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from modoor.core.db import session_scope
from modoor.platform.module_state import list_modules, set_module_enabled, sync_discovered_modules
from modoor.web.api_util import ctx_of, http_error, kit, require_user
from modoor.web.nav import clear_ui_cache
from builtin.base import domain as base_domain
from builtin.base.tbl import get_table_setting, upsert_table_setting

router = APIRouter(prefix="/api/base", tags=["base"])


class UserCreate(BaseModel):
    username: str | None = None
    realname: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    remark: str | None = None
    password: str | None = None
    team_id: int | None = None


class UserUpdate(BaseModel):
    realname: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    remark: str | None = None
    active: bool | None = None
    password: str | None = None
    team_id: int | None = None


class TeamCreate(BaseModel):
    name: str
    parent: int | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    parent: int | None = None
    active: bool | None = None


class RoleCreate(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None


class RoleAssign(BaseModel):
    user_id: int
    role_id: str


class RoleNodesUpdate(BaseModel):
    nodes: list[str]


class ModuleToggle(BaseModel):
    enabled: bool


class ConfigUpsert(BaseModel):
    mod: str
    type: str
    title: str | None = None
    data: Any = None


class TblUpsert(BaseModel):
    model: str
    using: str | None = None
    data: Any = None


@router.get("/users")
def api_list_users(
    request: Request,
    q: str | None = None,
    team_id: int | None = None,
) -> dict[str, Any]:
    user = require_user(request)
    with session_scope() as session:
        return base_domain.list_users(
            session, ctx_of(user), q=q, team_id=team_id, limit=200
        )


@router.post("/users")
def api_create_user(request: Request, body: UserCreate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            data = body.model_dump(exclude_unset=True)
            kwargs: dict[str, Any] = {
                "username": body.username,
                "realname": body.realname,
                "name": body.name,
                "phone": body.phone,
                "email": body.email,
                "remark": body.remark,
                "password": body.password,
            }
            if "team_id" in data:
                kwargs["team_id"] = data["team_id"]
            row = base_domain.create_user(session, ctx_of(user), **kwargs)
        return {"ok": True, "user": row}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.patch("/users/{user_key}")
def api_update_user(request: Request, user_key: str, body: UserUpdate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            ctx = ctx_of(user)
            target = base_domain.resolve_user_key(session, ctx, user_key)
            kwargs: dict[str, Any] = {
                "user_id": target.id,
                "realname": body.realname,
                "name": body.name,
                "phone": body.phone,
                "email": body.email,
                "remark": body.remark,
                "active": body.active,
                "password": body.password,
            }
            data = body.model_dump(exclude_unset=True)
            if "team_id" in data:
                kwargs["team_id"] = data["team_id"]
            row = base_domain.update_user(session, ctx, **kwargs)
        return {"ok": True, "user": row}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/users/{user_key}/roles")
def api_user_roles(request: Request, user_key: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            ctx = ctx_of(user)
            target = base_domain.resolve_user_key(session, ctx, user_key)
            assigned = base_domain.list_user_roles(session, ctx, user_id=target.id)
            roles = base_domain.list_roles(session, ctx, limit=200)["items"]
            payload = {
                "ok": True,
                "user_id": target.id,
                "roles": roles,
                "assigned": assigned["roles"],
            }
        return payload
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/users/{user_key}")
def api_delete_user(request: Request, user_key: str) -> dict[str, Any]:
    from modoor.core.errors import AppError

    user = require_user(request)
    try:
        with session_scope() as session:
            ctx = ctx_of(user)
            target = base_domain.resolve_user_key(session, ctx, user_key)
            if user.id == target.id:
                raise AppError("validation_error", "cannot delete the current user")
            base_domain.delete_user(session, ctx, user_id=target.id)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/teams/tree")
def api_team_tree(request: Request) -> dict[str, Any]:
    user = require_user(request)
    with session_scope() as session:
        return base_domain.list_team_tree(session, ctx_of(user))


@router.post("/teams")
def api_create_team(request: Request, body: TeamCreate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            row = base_domain.create_team(
                session, ctx_of(user), name=body.name, parent=body.parent
            )
        return {"ok": True, "team": row}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.patch("/teams/{team_id}")
def api_update_team(request: Request, team_id: int, body: TeamUpdate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            data = body.model_dump(exclude_unset=True)
            kwargs: dict[str, Any] = {"team_id": team_id}
            if "name" in data:
                kwargs["name"] = data["name"]
            if "active" in data:
                kwargs["active"] = data["active"]
            if "parent" in data:
                kwargs["parent"] = data["parent"]
            row = base_domain.update_team(session, ctx_of(user), **kwargs)
        return {"ok": True, "team": row}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/teams/{team_id}")
def api_delete_team(request: Request, team_id: int) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            base_domain.delete_team(session, ctx_of(user), team_id=team_id)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/roles")
def api_roles_bundle(request: Request) -> dict[str, Any]:
    user = require_user(request)
    ctx = ctx_of(user)
    with session_scope() as session:
        roles = base_domain.list_roles(session, ctx, limit=200)["items"]
        users = base_domain.list_users(session, ctx, limit=200)["items"]
        assignments = {
            u["id"]: base_domain.list_user_roles(session, ctx, user_id=u["id"])["roles"]
            for u in users
        }
        role_nodes = {
            r["id"]: base_domain.list_role_nodes(session, ctx, role_id=r["id"])["nodes"]
            for r in roles
        }
    catalog = base_domain.list_ability_catalog()
    return {
        "roles": roles,
        "users": users,
        "assignments": assignments,
        "role_nodes": role_nodes,
        "ability_catalog": catalog,
    }


@router.get("/roles/{role_id}/nodes")
def api_get_role_nodes(request: Request, role_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return base_domain.list_role_nodes(session, ctx_of(user), role_id=role_id)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.put("/roles/{role_id}/nodes")
def api_set_role_nodes(request: Request, role_id: str, body: RoleNodesUpdate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            return base_domain.set_role_nodes(
                session, ctx_of(user), role_id=role_id, nodes=body.nodes
            )
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/roles")
def api_create_role(request: Request, body: RoleCreate) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            row = base_domain.create_role(
                session,
                ctx_of(user),
                name=body.name,
                code=body.code,
                description=body.description,
            )
        return {"ok": True, "role": row}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/roles/{role_id}")
def api_delete_role(request: Request, role_id: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            base_domain.delete_role(session, ctx_of(user), role_id=role_id)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/roles/assign")
def api_assign_role(request: Request, body: RoleAssign) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            base_domain.assign_role(
                session, ctx_of(user), user_id=body.user_id, role_id=body.role_id
            )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.post("/roles/revoke")
def api_revoke_role(request: Request, body: RoleAssign) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            base_domain.revoke_role(
                session, ctx_of(user), user_id=body.user_id, role_id=body.role_id
            )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/modules")
def api_list_modules(request: Request) -> dict[str, Any]:
    require_user(request)
    clear_ui_cache()
    with session_scope() as session:
        sync_discovered_modules(session, kit().tenant())
        modules = list_modules(session, kit().tenant())
    return {"modules": modules}


@router.post("/modules/{module_id}/toggle")
def api_toggle_module(request: Request, module_id: str, body: ModuleToggle) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            tenant = kit().tenant()
            if body.enabled:
                from modoor.core.ctx import Ctx
                from modoor.platform.loader import ensure_module_enabled

                ctx = Ctx(
                    tenant=tenant,
                    user_id=int(user.id),
                    team_id=int(user.team_id or 0),
                )
                ensure_module_enabled(session, tenant, module_id, ctx=ctx)
            else:
                set_module_enabled(session, tenant, module_id, False)
        clear_ui_cache()
        return {"ok": True, "module_id": module_id, "enabled": body.enabled}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/config")
def api_list_config(request: Request, mod: str | None = None) -> dict[str, Any]:
    """列出 base_config（表 base_cfg）；可选 mod 过滤。fleet 首次访问会灌 dicts.json 种子。"""
    user = require_user(request)
    try:
        with session_scope() as session:
            ctx = ctx_of(user)
            if mod == "fleet":
                from addon.fleet.domain import load_dicts_catalog

                base_domain.ensure_config_seeded(
                    session, ctx, mod="fleet", catalog=load_dicts_catalog()
                )
            items = base_domain.list_configs(session, ctx, mod=mod)
            return {"items": items, "count": len(items)}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/config/item")
def api_get_config(request: Request, mod: str, type: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            ctx = ctx_of(user)
            if mod == "fleet":
                from addon.fleet.domain import load_dicts_catalog

                base_domain.ensure_config_seeded(
                    session, ctx, mod="fleet", catalog=load_dicts_catalog()
                )
            row = base_domain.get_config(session, ctx, mod=mod, type=type)
            if row is None:
                return {"item": None}
            return {"item": base_domain.config_row(row)}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.put("/config")
def api_put_config(request: Request, body: ConfigUpsert) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            item = base_domain.upsert_config(
                session,
                ctx_of(user),
                mod=body.mod,
                type=body.type,
                data=body.data,
                title=body.title,
            )
            return {"ok": True, "item": item}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.get("/tbl")
def api_get_tbl(request: Request, model: str, using: str = "default") -> dict[str, Any]:
    """全局列设置。没有记录时 item 为 null，列表用 tables.json 的默认列。"""
    user = require_user(request)
    try:
        with session_scope() as session:
            item = get_table_setting(session, ctx_of(user), model=model, using=using)
            return {"item": item}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.put("/tbl")
def api_put_tbl(request: Request, body: TblUpsert) -> dict[str, Any]:
    """保存全局列设置。data 为空则删除记录，恢复 tables.json 默认。"""
    user = require_user(request)
    try:
        with session_scope() as session:
            item = upsert_table_setting(
                session,
                ctx_of(user),
                model=body.model,
                using=body.using,
                data=body.data,
            )
            return {"ok": True, "item": item}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


@router.delete("/config")
def api_delete_config(request: Request, mod: str, type: str) -> dict[str, Any]:
    user = require_user(request)
    try:
        with session_scope() as session:
            ok = base_domain.delete_config(session, ctx_of(user), mod=mod, type=type)
            return {"ok": ok}
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc) from exc


def register(app, _kit) -> None:
    app.include_router(router)
