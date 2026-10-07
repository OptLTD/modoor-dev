"""Bootstrap tenant / admin / welcome wiki for local / first-run.

Demo business data (sale / fleet / dispatch) is NOT seeded here — use
``python scripts/seed_demo.py`` or ``make seed``.
"""

from __future__ import annotations

from sqlalchemy import select

from modoor.core.ctx import Ctx
from modoor.core.db import session_scope
from modoor.core.errors import AppError
from modoor.core.security import hash_password
from modoor.core.settings import Settings, get_settings
from modoor.platform.loader import ensure_modules_ready
from modoor.platform.module_state import enabled_module_ids, sync_discovered_modules
from builtin.base import domain as base_domain
from builtin.base.domain import SystemTenant, SystemUser


def _find_existing_tenant(
    session, *, tenant_id: int | None, tenant_name: str
) -> SystemTenant | None:
    if tenant_id is not None:
        return session.get(SystemTenant, tenant_id)
    return session.scalar(select(SystemTenant).where(SystemTenant.name == tenant_name))


def bootstrap(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    tenant_name = settings.modoor_tenant
    tenant_id_pref = settings.modoor_tenant_id
    admin_username = settings.modoor_admin_username
    admin_password = settings.modoor_admin_password

    created = {
        "tenant": False,
        "root_team": False,
        "admin_user": False,
        "admin_role": False,
        "welcome_wiki": False,
        "admin_password_reset": False,
    }

    with session_scope() as session:
        existing = _find_existing_tenant(
            session, tenant_id=tenant_id_pref, tenant_name=tenant_name
        )

        if existing is not None:
            # Tenant already present → skip tenant / head team / admin creation.
            tenant_id = int(existing.id)
            team_id = base_domain.root_team_id(session, tenant_id)
            created["tenant"] = False
            created["root_team"] = False
        else:
            ensured = base_domain.ensure_tenant(
                session, tenant_name, tenant_id=tenant_id_pref
            )
            tenant_id = int(ensured["tenant"]["id"])
            team_id = int(ensured["team"]["id"])
            created["tenant"] = ensured["created_tenant"]
            created["root_team"] = ensured["created_team"]

        sync_discovered_modules(session, tenant_id, settings)
        ensure_modules_ready(session, settings=settings, tenant=tenant_id)

        bootstrap_ctx = Ctx(tenant=tenant_id, user_id=0, team_id=team_id)

        if existing is not None:
            try:
                admin = base_domain.get_user(
                    session, bootstrap_ctx, username=admin_username
                )
            except AppError:
                row = session.scalar(
                    select(SystemUser)
                    .where(SystemUser.tenant == tenant_id)
                    .order_by(SystemUser.id)
                )
                if row is None:
                    raise AppError(
                        "bootstrap_error",
                        f"Tenant {tenant_id} exists but has no users; "
                        "cannot continue bootstrap without admin",
                    ) from None
                admin = base_domain.get_user(session, bootstrap_ctx, user_id=row.id)
        else:
            try:
                admin = base_domain.get_user(
                    session, bootstrap_ctx, username=admin_username
                )
            except AppError:
                admin = base_domain.create_user(
                    session,
                    bootstrap_ctx,
                    team_id=team_id,
                    realname="Administrator",
                    username=admin_username,
                    password=admin_password,
                )
                created["admin_user"] = True

            admin_id = int(admin["id"])
            row = base_domain.load_user(session, admin_id, tenant=tenant_id)
            if row and row.login is not None and not row.login.password:
                row.login.password = hash_password(admin_password)
                created["admin_password_reset"] = True
            if row and row.login is not None and row.login.current is None:
                row.login.current = tenant_id
            if row and row.login is not None and not (row.login.realname or "").strip():
                row.login.realname = "Administrator"
            if row and row.team_id != team_id:
                row.team_id = team_id

        admin_id = int(admin["id"])
        ctx = Ctx(tenant=tenant_id, user_id=admin_id, team_id=team_id)

        try:
            role = base_domain.get_role(session, ctx, code="admin")
        except AppError:
            role = base_domain.create_role(
                session,
                ctx,
                code="admin",
                name="Administrator",
                description="Full access",
            )
            created["admin_role"] = True

        role_id = role["id"]
        roles = base_domain.list_user_roles(session, ctx, user_id=admin_id)
        if not any(r["id"] == role_id for r in roles["roles"]):
            base_domain.assign_role(session, ctx, user_id=admin_id, role_id=role_id)

        enabled = enabled_module_ids(session, tenant_id)
        if "wiki" in enabled:
            from builtin.wiki import domain as wiki_domain

            projects = wiki_domain.list_projects(session, ctx)
            if projects["count"] == 0:
                created_proj = wiki_domain.create_project(
                    session,
                    ctx,
                    name="General",
                    description="Default wiki project",
                    home_title="Welcome",
                )
                home_id = created_proj["home_page"]["id"]
                wiki_domain.update_page(
                    session,
                    ctx,
                    page_id=home_id,
                    title="Welcome",
                    body=wiki_domain.markdown_to_blocks_json(
                        "# Welcome to Modoor\n\n"
                        "Bootstrap created this project.\n\n"
                        f"- Username: `{admin_username}`\n"
                        "- Open Base module for users and roles.\n"
                    ),
                )
                created["welcome_wiki"] = True

    return {
        "tenant": tenant_name,
        "tenant_id": tenant_id,
        "team_id": team_id,
        "admin_username": admin_username,
        "created": created,
    }
