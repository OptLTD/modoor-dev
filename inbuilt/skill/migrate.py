"""Idempotent skill_item schema upgrades."""

from __future__ import annotations

from sqlalchemy import text

from modoor.core.schema import table_columns, table_exists


def migrate(conn) -> None:
    if not table_exists(conn, "skill_item"):
        return
    cols = table_columns(conn, "skill_item")
    if "module" not in cols:
        conn.execute(
            text(
                "ALTER TABLE skill_item ADD COLUMN module VARCHAR(64) NOT NULL DEFAULT 'custom'"
            )
        )
        conn.execute(
            text(
                "UPDATE skill_item SET module = 'custom' WHERE module IS NULL OR module = ''"
            )
        )

    # Drop legacy unique(tenant, skill_key) — name may be constraint or index.
    conn.execute(text('ALTER TABLE skill_item DROP CONSTRAINT IF EXISTS uq_skill_item_tenant_key'))
    conn.execute(text('DROP INDEX IF EXISTS uq_skill_item_tenant_key'))
    conn.execute(
        text(
            'CREATE UNIQUE INDEX IF NOT EXISTS "uq_skill_item_tenant_module_key" '
            'ON "skill_item" (tenant, module, skill_key)'
        )
    )
    conn.execute(
        text(
            'CREATE INDEX IF NOT EXISTS "ix_skill_item_tenant_module" '
            'ON "skill_item" (tenant, module)'
        )
    )
    if "disabled" not in cols:
        conn.execute(
            text(
                "ALTER TABLE skill_item ADD COLUMN disabled BOOLEAN NOT NULL DEFAULT false"
            )
        )
