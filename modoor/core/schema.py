"""Reusable schema helpers for module migrations."""

from __future__ import annotations

from sqlalchemy import text


def table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": table},
        ).scalar()
    )


def table_columns(conn, table: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": table},
    ).all()
    return {str(name): str(dtype) for name, dtype in rows}


def ensure_unique_index(conn, name: str, table: str, columns: str) -> None:
    conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table}" ({columns})'))


def ensure_index(conn, name: str, table: str, columns: str) -> None:
    conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ({columns})'))


def ensure_partial_unique_index(conn, name: str, table: str, columns: str, where: str) -> None:
    conn.execute(
        text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table}" ({columns}) WHERE {where}'
        )
    )
