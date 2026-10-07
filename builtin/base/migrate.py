"""Schema patches for builtin.base (create_all does not alter column types)."""

from __future__ import annotations

from sqlalchemy import text


def migrate(conn) -> None:
    _fix_oplog_action_to_varchar(conn)
    _fix_oplog_id_width(conn)
    _ensure_oplog_model_column(conn)
    _ensure_user_login_columns(conn)
    _ensure_base_tbl(conn)


def _col_type(conn, table: str, column: str) -> tuple[str, int | None] | None:
    row = conn.execute(
        text(
            """
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table
              AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).fetchone()
    if row is None:
        return None
    return str(row[0] or "").lower(), row[1]


def _fix_oplog_action_to_varchar(conn) -> None:
    """Early SystemOplog.action was JSON; audit + duolali actions are strings."""
    info = _col_type(conn, "base_oplog", "action")
    if info is None:
        return
    data_type, _ = info
    if data_type not in ("json", "jsonb"):
        return
    conn.execute(
        text(
            """
            ALTER TABLE base_oplog
            ALTER COLUMN action TYPE varchar(64)
            USING (
              CASE
                WHEN action IS NULL THEN NULL
                WHEN jsonb_typeof(action::jsonb) = 'string'
                  THEN left(action #>> '{}', 64)
                ELSE left(action::text, 64)
              END
            )
            """
        )
    )


def _fix_oplog_id_width(conn) -> None:
    """Sync fingerprints are sha1 hex (40); early table used varchar(36)."""
    info = _col_type(conn, "base_oplog", "id")
    if info is None:
        return
    data_type, length = info
    if data_type not in ("character varying", "varchar"):
        return
    if length is not None and length >= 40:
        return
    conn.execute(text("ALTER TABLE base_oplog ALTER COLUMN id TYPE varchar(40)"))


def _ensure_user_login_columns(conn) -> None:
    """base.user 记下指向的档案模型和编号，列名是 model、refer。"""
    if _col_type(conn, "base_user", "id") is None:
        return
    _rename_user_column(conn, "profile_model", "model")
    _rename_user_column(conn, "profile_refer", "refer")


def _rename_user_column(conn, old: str, new: str) -> None:
    has_new = _col_type(conn, "base_user", new) is not None
    has_old = _col_type(conn, "base_user", old) is not None
    if has_old and not has_new:
        conn.execute(text(f"ALTER TABLE base_user RENAME COLUMN {old} TO {new}"))
        return
    if not has_new:
        conn.execute(
            text(f"ALTER TABLE base_user ADD COLUMN {new} varchar(64) NOT NULL DEFAULT ''")
        )
    if has_old:
        conn.execute(text(f"ALTER TABLE base_user DROP COLUMN {old}"))


def _ensure_base_tbl(conn) -> None:
    """列设置。using 是保留相关词，建列时加引号。"""
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS base_tbl (
              id varchar(36) PRIMARY KEY,
              tenant integer NOT NULL,
              model varchar(64) NOT NULL,
              "using" varchar(64) NOT NULL DEFAULT 'default',
              level varchar(16) NOT NULL DEFAULT 'global',
              data json NOT NULL DEFAULT '{}',
              updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_base_tbl_tenant ON base_tbl (tenant)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_base_tbl_model ON base_tbl (model)"))
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_base_tbl_tenant_model_using_level
            ON base_tbl (tenant, model, "using", level)
            """
        )
    )


def _ensure_oplog_model_column(conn) -> None:
    """Add top-level model (align duolali biz_sys_oplogs.model) and backfill."""
    if _col_type(conn, "base_oplog", "id") is None:
        return
    if _col_type(conn, "base_oplog", "model") is None:
        conn.execute(
            text(
                "ALTER TABLE base_oplog ADD COLUMN model varchar(64) NOT NULL DEFAULT ''"
            )
        )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_base_oplog_tenant_model_code
            ON base_oplog (tenant, model, code)
            """
        )
    )
    # Backfill from JSON payload written by local audit / earlier sync.
    conn.execute(
        text(
            """
            UPDATE base_oplog
            SET model = left(COALESCE(values->>'model', ''), 64)
            WHERE (model IS NULL OR model = '')
              AND values IS NOT NULL
              AND COALESCE(values->>'model', '') <> ''
            """
        )
    )
