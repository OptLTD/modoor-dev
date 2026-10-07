"""Idempotent schema patches for addon.sale (none — ORM create_all is enough)."""

from __future__ import annotations


def migrate(conn) -> None:
    _ = conn
