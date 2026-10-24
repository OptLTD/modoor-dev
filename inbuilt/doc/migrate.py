"""Add asset origin columns. create_all does not alter an existing doc_asset."""

from __future__ import annotations

from sqlalchemy import text


def migrate(conn) -> None:
    _ensure_origin_columns(conn)


def _has_column(conn, table: str, column: str) -> bool | None:
    """None when the table itself is missing."""
    table_row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table
            """
        ),
        {"table": table},
    ).fetchone()
    if table_row is None:
        return None
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table
              AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).fetchone()
    return row is not None


def _ensure_origin_columns(conn) -> None:
    specs = (
        ("model", "varchar(128)"),
        ("uukey", "varchar(64)"),
        ("field", "varchar(128)"),
    )
    for column, ddl in specs:
        exists = _has_column(conn, "doc_asset", column)
        if exists is None or exists:
            continue
        conn.execute(
            text(
                f"ALTER TABLE doc_asset ADD COLUMN {column} {ddl} NOT NULL DEFAULT ''"
            )
        )
    if _has_column(conn, "doc_asset", "id") is None:
        return
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_doc_asset_model ON doc_asset (model)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_doc_asset_uukey ON doc_asset (uukey)"))
