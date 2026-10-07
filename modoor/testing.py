"""Postgres-only test helpers. Uses `modoor_test` so `make dev` data is not wiped."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from modoor.core.db import init_db, reset_engine
from modoor.core.settings import Settings, get_settings

DEFAULT_TEST_URL = "postgresql+psycopg://modoor:modoor@127.0.0.1:5432/modoor_test"


def _require_postgres(raw: str):
    parsed = make_url(raw)
    if not parsed.drivername.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL / TEST_DATABASE_URL must be PostgreSQL")
    return parsed


def test_database_url() -> str:
    """Host/port follow .env `DATABASE_URL`; database is always `modoor_test` unless TEST_DATABASE_URL is set."""
    explicit = (os.environ.get("TEST_DATABASE_URL") or "").strip()
    if explicit:
        return _require_postgres(explicit).render_as_string(hide_password=False)
    app = (os.environ.get("DATABASE_URL") or "").strip()
    if not app:
        app = Settings().database_url
    return _require_postgres(app).set(database="modoor_test").render_as_string(
        hide_password=False
    )


def ensure_database(url: str) -> None:
    parsed = make_url(url)
    name = parsed.database
    if not name:
        raise RuntimeError("DATABASE_URL must include a database name")
    admin = parsed.set(database="postgres")
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": name},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()


def configure_test_db(monkeypatch, **env: str) -> None:
    url = test_database_url()
    ensure_database(url)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("MODOOR_JOBS_INPROCESS", "0")
    monkeypatch.setenv("MODOOR_DOC_OCR", "0")
    # Existing suite expects full schema; lazy-enable is covered by dedicated tests.
    if "MODOOR_LOAD_ALL_MODULES" not in env:
        monkeypatch.setenv("MODOOR_LOAD_ALL_MODULES", "1")
    # Avoid local .env MODOOR_ADMIN / TENANT pipe forms leaking into tests.
    if "MODOOR_ADMIN" not in env:
        monkeypatch.delenv("MODOOR_ADMIN", raising=False)
        monkeypatch.setenv("MODOOR_ADMIN", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    reset_engine()
    init_db(get_settings(), recreate=True)
